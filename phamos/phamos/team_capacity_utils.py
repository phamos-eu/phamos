import frappe
from datetime import timedelta


def _get_team_capacity_cache():
    """Return request-scoped cache for expensive team capacity lookups."""
    cache = getattr(frappe.local, "_team_capacity_cache", None)
    if cache is None:
        cache = {
            "wwh_by_employee": {},
            "hours_by_wwh_day": {},
            "daily_hours": {},
            "holidays_by_period": {},
            "leave_apps_by_period": {},
            "leave_hours_by_period": {},
        }
        frappe.local._team_capacity_cache = cache
    return cache


def get_employee_daily_hours(employee, work_date):
    """Return an employee's scheduled working hours for a specific date."""
    cache = _get_team_capacity_cache()
    daily_key = (employee, work_date)
    if daily_key in cache["daily_hours"]:
        return cache["daily_hours"][daily_key]

    day_name = work_date.strftime("%A")
    if employee in cache["wwh_by_employee"]:
        wwh = cache["wwh_by_employee"][employee]
    else:
        wwh = frappe.db.get_value("Weekly Working Hours", {"employee": employee}, "name")
        cache["wwh_by_employee"][employee] = wwh

    if not wwh:
        cache["daily_hours"][daily_key] = 0
        return 0

    day_hours_key = (wwh, day_name)
    if day_hours_key in cache["hours_by_wwh_day"]:
        hours = cache["hours_by_wwh_day"][day_hours_key]
    else:
        hours = frappe.db.get_value(
            "Daily Hours Detail",
            {"parent": wwh, "day": day_name},
            "hours"
        )
        cache["hours_by_wwh_day"][day_hours_key] = hours or 0

    cache["daily_hours"][daily_key] = hours or 0
    return cache["daily_hours"][daily_key]


def get_period_leave_hours(employee, period_start, period_end):
    """Return an employee's total holiday + approved Leave Application hours within [period_start, period_end]."""
    cache = _get_team_capacity_cache()
    leave_hours_key = (employee, period_start, period_end)
    if leave_hours_key in cache["leave_hours_by_period"]:
        return cache["leave_hours_by_period"][leave_hours_key]

    total = 0.0
    holiday_dates = set()

    holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
    if holiday_list:
        holidays_key = (holiday_list, period_start, period_end)
        if holidays_key in cache["holidays_by_period"]:
            holidays = cache["holidays_by_period"][holidays_key]
        else:
            holidays = frappe.db.get_all(
                "Holiday",
                filters={
                    "parent": holiday_list,
                    "holiday_date": ["between", [period_start, period_end]]
                },
                fields=["holiday_date"]
            )
            cache["holidays_by_period"][holidays_key] = holidays

        for h in holidays:
            holiday_dates.add(h.holiday_date)
            total += get_employee_daily_hours(employee, h.holiday_date)

    leave_apps_key = (employee, period_start, period_end)
    if leave_apps_key in cache["leave_apps_by_period"]:
        leave_apps = cache["leave_apps_by_period"][leave_apps_key]
    else:
        leave_apps = frappe.db.get_all(
            "Leave Application",
            filters={
                "employee": employee,
                "docstatus": 1,
                "from_date": ["<=", period_end],
                "to_date": [">=", period_start],
            },
            fields=["from_date", "to_date", "half_day"]
        )
        cache["leave_apps_by_period"][leave_apps_key] = leave_apps

    for leave in leave_apps:
        day = max(leave.from_date, period_start)
        last_day = min(leave.to_date, period_end)
        while day <= last_day:
            if day not in holiday_dates:
                hrs = get_employee_daily_hours(employee, day)
                if leave.half_day:
                    hrs = hrs / 2
                total += hrs
            day += timedelta(days=1)

    cache["leave_hours_by_period"][leave_hours_key] = total
    return total


def get_team_employees(team_names=None):
    """Return {team_name: [employee, ...]} from the Team Members child table."""
    from frappe.query_builder import DocType

    TeamMember = DocType("Team Members")
    query = (
        frappe.qb.from_(TeamMember)
        .select(TeamMember.parent, TeamMember.employee)
        .where(TeamMember.parenttype == "Team")
    )
    if team_names:
        query = query.where(TeamMember.parent.isin(team_names))

    team_employees = {}
    for row in query.run(as_dict=True):
        team_employees.setdefault(row.parent, [])
        if row.employee:
            team_employees[row.parent].append(row.employee)
    return team_employees


def calculate_live_team_capacity(employees, period_start, period_end):
    """
    Live capacity for a group of employees over [period_start, period_end]: each
    employee's scheduled hours for every day in the period, minus their approved
    Leave Application / Holiday hours in that same period. Mirrors the formula
    `Team.total_team_capacity_daily` uses per day (doctype/team/team.py), so it
    matches what the nightly Team Capacity Ledger job would eventually record
    for dates it hasn't reached yet.
    """
    total = 0.0
    for employee in employees:
        day = period_start
        while day <= period_end:
            total += get_employee_daily_hours(employee, day)
            day += timedelta(days=1)
        total -= get_period_leave_hours(employee, period_start, period_end)
    return max(total, 0.0)
