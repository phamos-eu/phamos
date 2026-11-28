import frappe
from datetime import timedelta

from frappe.utils import getdate


def _get_team_capacity_cache():
    """Return request-scoped cache for expensive team capacity lookups."""
    cache = getattr(frappe.local, "_team_capacity_cache", None)
    if cache is None:
        cache = {
            "wwh_by_employee": {},
            "daily_hours": {},
            "holidays_by_period": {},
            "leave_apps_by_period": {},
            "leave_hours_by_period": {},
        }
        frappe.local._team_capacity_cache = cache
    return cache


def get_employee_daily_hours(employee, work_date):
    """Return an employee's scheduled working hours for a specific date.

    From the submitted Weekly Working Hours (HR Addon) whose validity covers the date, as HR Addon
    itself reads them (workday.get_employee_default_work_hour). A draft or cancelled record, or
    one valid at another time, does not count (#1983). Without a valid record: the weekly hours of
    the submitted Employment Contract valid that day, spread over Monday to Friday (#1975).
    Neither: 0.
    """
    return get_employee_scheduled_hours(employee, work_date)[0]


def get_employee_scheduled_hours(employee, work_date):
    """(hours, source) of `employee` on `work_date`. source: "wwh" (Weekly Working Hours),
    "contract" (Employment Contract, weekly hours / 5 on Monday to Friday) or None (unknown)."""
    cache = _get_team_capacity_cache()
    daily_key = (employee, work_date)
    if daily_key in cache["daily_hours"]:
        return cache["daily_hours"][daily_key]

    if employee not in cache["wwh_by_employee"]:
        cache["wwh_by_employee"][employee] = _weekly_working_hours(employee)

    result = (0, None)
    for record in cache["wwh_by_employee"][employee]:
        if record["valid_from"] <= work_date <= (record["valid_to"] or work_date):
            result = (record["hours"].get(work_date.strftime("%A"), 0), "wwh")
            break
    else:
        contract = _contract_on(employee, work_date)
        if contract:
            weekday = work_date.weekday() < 5
            result = ((contract.weekly_hours or 0) / 5 if weekday else 0, "contract")

    cache["daily_hours"][daily_key] = result
    return result


def _contract_on(employee, on_date):
    """The submitted Employment Contract of `employee` valid on `on_date`, latest start first."""
    cache = _get_team_capacity_cache()
    contracts = cache.setdefault("contracts_by_employee", {})
    if employee not in contracts:
        contracts[employee] = (
            frappe.get_all(
                "Employment Contract",
                filters={"employee": employee, "docstatus": 1},
                fields=["effective_from", "valid_until", "weekly_hours", "fte_percentage"],
                order_by="effective_from desc",
            )
            if frappe.db.exists("DocType", "Employment Contract")
            else []
        )
    for contract in contracts[employee]:
        if contract.effective_from and contract.effective_from <= on_date <= (contract.valid_until or on_date):
            return contract
    return None


# Approved leave only: HRMS also submits Leave Applications with the status Rejected.
LEAVE_FIELDS = ["from_date", "to_date", "half_day", "half_day_date", "leave_type"]


def leave_day_share(leave, day):
    """How much of the day a Leave Application takes: 0.5 on its half day, otherwise 1.

    HRMS marks one day of a leave as the half day (half_day_date); a one-day leave with half_day
    is that day. The other days of a longer leave are whole days.
    """
    if not leave.half_day:
        return 1
    half_day = leave.half_day_date or (leave.from_date if leave.from_date == leave.to_date else None)
    return 0.5 if half_day and getdate(half_day) == day else 1


def get_employee_weekly_hours(employee, on_date):
	"""Scheduled hours per week on `on_date`: the hours per weekday of the submitted Weekly Working
	Hours valid then, summed; without one, the weekly hours of the submitted Employment Contract
	valid then; otherwise 0 (#1974)."""
	cache = _get_team_capacity_cache()
	if employee not in cache["wwh_by_employee"]:
		cache["wwh_by_employee"][employee] = _weekly_working_hours(employee)
	for record in cache["wwh_by_employee"][employee]:
		if record["valid_from"] <= on_date <= (record["valid_to"] or on_date):
			return sum(record["hours"].values())

	contract = _contract_on(employee, on_date)
	return (contract.weekly_hours or 0) if contract else 0


def employee_holiday_list(employee):
	"""The employee's Holiday List, else their company's default, as HRMS reads it; None if neither."""
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	return get_holiday_list_for_employee(employee, raise_exception=False) or None


def _weekly_working_hours(employee):
    """The employee's submitted Weekly Working Hours: validity and hours per weekday, newest first."""
    if not frappe.db.exists("DocType", "Weekly Working Hours"):
        # HR Addon is not installed on this site
        return []
    records = frappe.get_all(
        "Weekly Working Hours",
        filters={"employee": employee, "docstatus": 1},
        fields=["name", "valid_from", "valid_to"],
        # newest first; on the same start date the later record wins
        order_by="valid_from desc, creation desc",
    )
    for record in records:
        rows = frappe.get_all(
            "Daily Hours Detail",
            filters={"parent": record.name, "parenttype": "Weekly Working Hours"},
            fields=["day", "hours"],
        )
        record["hours"] = {row.day: row.hours or 0 for row in rows}
    return records


def get_period_leave_hours(employee, period_start, period_end):
    """Return an employee's total holiday + approved Leave Application hours within [period_start, period_end]."""
    cache = _get_team_capacity_cache()
    leave_hours_key = (employee, period_start, period_end)
    if leave_hours_key in cache["leave_hours_by_period"]:
        return cache["leave_hours_by_period"][leave_hours_key]

    total = 0.0
    holiday_dates = set()

    holiday_list = employee_holiday_list(employee)
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
                "status": "Approved",
                "from_date": ["<=", period_end],
                "to_date": [">=", period_start],
            },
            fields=LEAVE_FIELDS
        )
        cache["leave_apps_by_period"][leave_apps_key] = leave_apps

    for leave in leave_apps:
        day = max(leave.from_date, period_start)
        last_day = min(leave.to_date, period_end)
        while day <= last_day:
            if day not in holiday_dates:
                total += get_employee_daily_hours(employee, day) * leave_day_share(leave, day)
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
