import json
import frappe
from frappe.utils import formatdate

def get_team_capacity_avg(from_month=None, to_month=None, team=None):
    conditions = []
    values = []

    if team:
        conditions.append("team = %s")
        values.append(str(team))

    if from_month:
        conditions.append("date >= %s")
        values.append(from_month + "-01")

    if to_month:
        conditions.append("date <= LAST_DAY(%s)")
        values.append(to_month + "-01")

    where_clause = " AND ".join(conditions)
    if where_clause:
        where_clause = "WHERE " + where_clause

    result = frappe.db.sql(f"""
        SELECT
            DATE_FORMAT(date, '%%Y-%%m') AS month_and_year,
            COALESCE(SUM(total_team_capacity_daily), 0) AS avg_capacity
        FROM `tabTeam Capacity Ledger`
        {where_clause}
        GROUP BY DATE_FORMAT(date, '%%Y-%%m')
        ORDER BY month_and_year
    """, values, as_dict=True)

    return result



@frappe.whitelist()
def get_chart_data(from_date=None, to_date=None, team=None, implementation=None):
    from_month = from_date[:7] if from_date else None
    to_month = to_date[:7] if to_date else None

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
        if team:
            filters["team"] = team

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
        team=team
    )
    return {
        "planning": planning_filtered,
        "prediction": prediction_filtered,
        "internal_projects": internal_project_filtered,
        "implementation_teams": implementation_teams,
        "team_capacity_avg": team_capacity_avg 
    }



