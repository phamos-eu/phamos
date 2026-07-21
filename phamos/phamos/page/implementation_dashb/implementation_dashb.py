import json
import frappe
from calendar import monthrange
from datetime import date
from frappe.utils import formatdate
from phamos.phamos.team_capacity_utils import get_team_employees, calculate_live_team_capacity


def _month_range(from_month, to_month):
    """Return 'YYYY-MM' strings from from_month to to_month inclusive."""
    if not from_month or not to_month:
        return []
    start_year, start_mon = (int(p) for p in from_month.split('-'))
    end_year, end_mon = (int(p) for p in to_month.split('-'))
    months = []
    year, mon = start_year, start_mon
    while (year, mon) <= (end_year, end_mon):
        months.append(f"{year:04d}-{mon:02d}")
        mon += 1
        if mon > 12:
            mon = 1
            year += 1
    return months


def get_team_capacity_avg(from_month=None, to_month=None, teams=None):
    conditions = []
    values = []

    if teams:
        placeholders = ", ".join(["%s"] * len(teams))
        conditions.append(f"team IN ({placeholders})")
        values.extend(teams)

    if from_month:
        conditions.append("date >= %s")
        values.append(from_month + "-01")

    if to_month:
        conditions.append("date <= LAST_DAY(%s)")
        values.append(to_month + "-01")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    ledger_result = frappe.db.sql(f"""
        SELECT
            DATE_FORMAT(date, '%%Y-%%m') AS month_and_year,
            COALESCE(SUM(total_team_capacity_daily), 0) AS avg_capacity
        FROM `tabTeam Capacity Ledger`
        {where_clause}
        GROUP BY DATE_FORMAT(date, '%%Y-%%m')
        ORDER BY month_and_year
    """, values, as_dict=True)

    capacity_by_month = {row.month_and_year: row.avg_capacity for row in ledger_result}

    # The Team Capacity Ledger only has entries for dates the nightly job has
    # already run for (today and earlier), so future months are missing here.
    # Compute those live instead of leaving them out, so approved Leave
    # Applications still reduce future capacity, matching Team Capacity Overview.
    missing_months = [m for m in _month_range(from_month, to_month) if m not in capacity_by_month]
    if missing_months:
        team_employees = get_team_employees(teams)
        employees = [emp for emps in team_employees.values() for emp in emps]
        for month in missing_months:
            year, mon = (int(p) for p in month.split('-'))
            month_start = date(year, mon, 1)
            month_end = date(year, mon, monthrange(year, mon)[1])
            capacity_by_month[month] = calculate_live_team_capacity(employees, month_start, month_end)

    return [
        {"month_and_year": month, "avg_capacity": capacity_by_month[month]}
        for month in sorted(capacity_by_month)
    ]



@frappe.whitelist()
def get_chart_data(from_date=None, to_date=None, team=None, implementation=None, department=None):
    from_month = from_date[:7] if from_date else None
    to_month = to_date[:7] if to_date else None
    team_list = [t.strip() for t in team.split(',') if t.strip()] if team else []
    department_list = [d.strip() for d in department.split(',') if d.strip()] if department else []

    def is_within_range(month_year):
        return (not from_month or month_year >= from_month) and (not to_month or month_year <= to_month)

    planning = []
    prediction = []
    implementation_teams = {}  # Map implementation name to team

    if implementation:
        impl_list = [i.strip() for i in implementation.split(',') if i.strip()]
        for impl_name in impl_list:
            full_doc = frappe.get_doc("Implementation", impl_name)
            implementation_teams[impl_name] = full_doc.team or "Unassigned"
            
            for row in (full_doc.resource_planning or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl_name
                planning.append(row_dict)

            for row in (full_doc.resource_planning_prediction or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl_name
                prediction.append(row_dict)
    else:
        filters = {}
        if team_list:
            filters["team"] = ["in", team_list]
        if department_list:
            filters["department"] = ["in", department_list]

        # Get implementations that should NOT be excluded (i.e., not purely internal)
        all_impls = frappe.get_all("Implementation", filters=filters, fields=["name", "team"])
        
        # Identify implementations that only have internal projects (to exclude them)
        internal_only_implementations = set()
        for impl in all_impls:
            projects = frappe.db.get_all(
                "Project",
                filters={"custom_implementation": impl.name},
                fields=["name", "custom_is_internal_project"]
            )
            if projects:
                # If ALL projects are internal, mark this implementation for exclusion
                if all(p.get("custom_is_internal_project") == 1 for p in projects):
                    internal_only_implementations.add(impl.name)
        
        for impl in all_impls:
            # Skip implementations that are purely internal (they'll be aggregated separately)
            if impl.name in internal_only_implementations:
                continue
                
            implementation_teams[impl.name] = impl.team or "Unassigned"
            full_doc = frappe.get_doc("Implementation", impl.name)
            
            for row in (full_doc.resource_planning or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl.name
                planning.append(row_dict)

            for row in (full_doc.resource_planning_prediction or []):
                row_dict = row.as_dict()
                row_dict["implementation_name"] = impl.name
                prediction.append(row_dict)

    # 🔹 Internal Projects - Get billable/non-billable breakdown
    internal_projects = frappe.get_all(
        "Project",
        filters={"custom_is_internal_project": 1},
        pluck="name"
    )

    internal_project_data = []
    if internal_projects:
        placeholders = ', '.join(['%s'] * len(internal_projects))
        internal_project_data = frappe.db.sql(f"""
            SELECT 
                DATE_FORMAT(tl.from_time, '%%Y-%%m') as month_and_year,
                SUM(CASE WHEN tl.is_billable = 1 THEN tl.hours ELSE 0 END) as billable_time_spent,
                SUM(CASE WHEN COALESCE(tl.is_billable, 0) = 0 THEN tl.hours ELSE 0 END) as non_billable_time_spent,
                'Internal Projects' as implementation_name
            FROM `tabTimesheet` t
            JOIN `tabTimesheet Detail` tl ON tl.parent = t.name
            WHERE t.parent_project IN ({placeholders})
              AND t.docstatus IN (1,0)
            GROUP BY DATE_FORMAT(tl.from_time, '%%Y-%%m')
            ORDER BY month_and_year
        """, internal_projects, as_dict=True)
    
    # Add Internal Projects to implementation_teams mapping
    if internal_project_data:
        implementation_teams['Internal Projects'] = 'Internal Projects'

    # Filter by date
    planning_filtered = [row for row in planning if row.month_and_year and is_within_range(row.month_and_year)]
    prediction_filtered = [row for row in prediction if row.month_and_year and is_within_range(row.month_and_year)]
    internal_project_filtered = [row for row in internal_project_data if row.month_and_year and is_within_range(row.month_and_year)]

    team_capacity_avg = get_team_capacity_avg(
        from_month=from_month,
        to_month=to_month,
        teams=team_list
    )
    return {
        "planning": planning_filtered,
        "prediction": prediction_filtered,
        "internal_projects": internal_project_filtered,
        "implementation_teams": implementation_teams,
        "team_capacity_avg": team_capacity_avg 
    }



