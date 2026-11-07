# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employees list with leave statistics in the Human Resources Cockpit (phamos/phamos#1835).

Decisions of #1833:
- System Manager, HR Manager and HR User see the list (Decision 2).
- Leave balances come from HRMS (`get_leave_details`), the same numbers as My Leave, one entry
  per leave type and never added up across types (Decisions 1, 6 and 7).
- Sick days are health data (Art. 9 GDPR): only HR Manager and System Manager get them, as a
  count for the year. For everyone else the key is left out of the response, not just hidden
  in the UI. Sick leave types are also kept out of the leave columns, last/next leave and
  pending applications, so HR User can't see a sick absence there (Decisions 4 and 7).
- Birthday is day and month only (Decision 4).
- FTE and contract end only for users who can read Employment Contract (Decision 2).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Max, Min
from frappe.utils import flt, getdate, nowdate

from phamos.phamos.doctype.employment_contract.employment_contract import get_active_contract
from phamos.phamos.hr import sick_leave

ROLES = {"System Manager", "HR Manager", "HR User"}
SICK_DAYS_ROLES = {"System Manager", "HR Manager"}
STATUSES = ("Active", "Left", "All")
EMPLOYEE_FIELDS = [
	"name",
	"employee_name",
	"department",
	"designation",
	"company",
	"status",
	"date_of_joining",
	"relieving_date",
	"date_of_birth",
]


def _check_access() -> set[str]:
	roles = set(frappe.get_roles())
	if not roles & ROLES:
		frappe.throw(_("Only HR users can see the employees list."), frappe.PermissionError)
	return roles


@frappe.whitelist()
def get_employees(status: str = "Active", company: str | None = None, search: str | None = None) -> dict:
	"""Employees with HR and leave statistics, plus what the list may show to this user."""
	roles = _check_access()
	if status not in STATUSES:
		frappe.throw(_("Unknown status {0}.").format(status))
	can_see_sick_days = bool(roles & SICK_DAYS_ROLES)
	can_see_contracts = bool(frappe.has_permission("Employment Contract", "read"))
	today = getdate(nowdate())

	filters = {}
	if status != "All":
		filters["status"] = status
	if company:
		filters["company"] = company
	or_filters = None
	if search and search.strip():
		term = f"%{search.strip()}%"
		or_filters = {"employee_name": ("like", term), "name": ("like", term)}
	employees = frappe.get_list(
		"Employee",
		filters=filters,
		or_filters=or_filters,
		fields=EMPLOYEE_FIELDS,
		order_by="employee_name asc",
		limit_page_length=0,
	)

	sick_types = sick_leave.get_sick_leave_types()
	names = [e.name for e in employees]
	leave_dates = _leave_dates(names, sick_types, today)
	sick_days = sick_leave.get_sick_days(names, *sick_leave.year_bounds(today)) if can_see_sick_days else None

	rows = [
		_employee_row(employee, today, sick_types, leave_dates, sick_days, can_see_sick_days, can_see_contracts)
		for employee in employees
	]

	return {
		"employees": rows,
		"leave_types": _leave_types(rows),
		"can_see_sick_days": can_see_sick_days,
		"can_see_contracts": can_see_contracts,
		"sick_types_configured": bool(sick_types),
		"companies": frappe.get_all("Company", pluck="name", order_by="name asc"),
	}


@frappe.whitelist()
def get_employee(name: str) -> dict:
	"""One employee for the detail dialog: the list row plus this year's leave and the contract.

	Same access rules as the list. Sick leave never appears among the applications; HR Manager
	gets its count only. The contract comes without salary fields.
	"""
	roles = _check_access()
	can_see_sick_days = bool(roles & SICK_DAYS_ROLES)
	can_see_contracts = bool(frappe.has_permission("Employment Contract", "read"))
	today = getdate(nowdate())
	employee = frappe.db.get_value("Employee", name, EMPLOYEE_FIELDS, as_dict=True)
	if not employee:
		frappe.throw(_("Employee {0} not found.").format(name), frappe.DoesNotExistError)

	sick_types = sick_leave.get_sick_leave_types()
	leave_dates = _leave_dates([name], sick_types, today)
	sick_days = sick_leave.get_sick_days([name], *sick_leave.year_bounds(today)) if can_see_sick_days else None
	row = _employee_row(employee, today, sick_types, leave_dates, sick_days, can_see_sick_days, can_see_contracts)
	row["applications"] = _applications(name, sick_types, today)
	row["holidays"] = _holidays(name, today)
	if can_see_contracts:
		row["contract"] = _contract(name, _on_date(employee, today))
	row["can_see_sick_days"] = can_see_sick_days
	row["can_see_contracts"] = can_see_contracts
	row["sick_types_configured"] = bool(sick_types)
	return row


def _on_date(employee, today):
	"""A leaver's numbers stop at the relieving date (#1833, Decision 8)."""
	return min(today, getdate(employee.relieving_date)) if employee.relieving_date else today


def _employee_row(employee, today, sick_types, leave_dates, sick_days, can_see_sick_days, can_see_contracts) -> dict:
	on_date = _on_date(employee, today)
	row = {
		"employee": employee.name,
		"employee_name": employee.employee_name,
		"department": employee.department,
		"designation": employee.designation,
		"company": employee.company,
		"status": employee.status,
		"years_in_company": _years(employee.date_of_joining, on_date),
		"birthday": getdate(employee.date_of_birth).strftime("%m-%d") if employee.date_of_birth else None,
		"leave": _leave_balance(employee.name, on_date, sick_types),
		**leave_dates.get(employee.name, {"last_leave": None, "next_leave": None, "pending_count": 0}),
	}
	if can_see_sick_days:
		row["sick_days"] = sick_days[employee.name] if sick_days is not None else None
	if can_see_contracts:
		contract = get_active_contract(employee.name, on_date)
		row["fte_percentage"] = contract.fte_percentage if contract else None
		row["contract_end"] = contract.valid_until if contract else None
	return row


def _applications(employee: str, sick_types, today) -> list[dict]:
	"""This calendar year's Leave Applications, newest first, without sick leave.

	Rejected and cancelled ones are included; the heatmap draws them muted (PM, 2026-11-07).
	"""
	year_start, year_end = sick_leave.year_bounds(today)
	filters = {
		"employee": employee,
		"from_date": ("<=", year_end),
		"to_date": (">=", year_start),
	}
	if sick_types:
		filters["leave_type"] = ("not in", sick_types)
	return frappe.get_all(
		"Leave Application",
		filters=filters,
		fields=[
			"name",
			"leave_type",
			"from_date",
			"to_date",
			"half_day",
			"half_day_date",
			"total_leave_days",
			"status",
			"docstatus",
			"leave_approver_name",
			"description",
			"posting_date",
		],
		order_by="from_date desc",
	)


def _holidays(employee: str, today) -> list[dict]:
	"""This year's holidays and weekly offs from the employee's holiday list, for the heatmap."""
	from hrms.hr.utils import get_holidays_for_employee

	year_start, year_end = sick_leave.year_bounds(today)
	return [
		{"date": h.holiday_date, "description": h.description, "weekly_off": bool(h.weekly_off)}
		for h in get_holidays_for_employee(employee, year_start, year_end, raise_exception=False)
	]


def _contract(employee: str, on_date) -> dict | None:
	"""The contract in force, with its leave fields; never salary (CAPACITY_FIELDS has none)."""
	contract = get_active_contract(employee, on_date)
	if not contract:
		return None
	leave = frappe.db.get_value(
		"Employment Contract", contract.name, ["working_days_per_week", "leave_days_per_year"], as_dict=True
	)
	return {
		"name": contract.name,
		"contract_type": contract.contract_type,
		"effective_from": contract.effective_from,
		"valid_until": contract.valid_until,
		"fte_percentage": contract.fte_percentage,
		"weekly_hours": contract.weekly_hours,
		"working_days_per_week": leave.working_days_per_week,
		"leave_days_per_year": leave.leave_days_per_year,
	}


def _years(date_of_joining, on_date) -> float | None:
	if not date_of_joining:
		return None
	return max(flt((getdate(on_date) - getdate(date_of_joining)).days / 365.25, 1), 0)


def _leave_balance(employee: str, on_date, sick_types) -> dict:
	"""Allocated, taken and left per leave type from HRMS, the same numbers as My Leave."""
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	allocations = get_leave_details(employee, on_date).get("leave_allocation") or {}
	return {
		leave_type: {
			"allocated": flt(values.get("total_leaves")),
			"taken": flt(values.get("leaves_taken")),
			"left": flt(values.get("remaining_leaves")),
		}
		for leave_type, values in allocations.items()
		if leave_type not in sick_types
	}


def _leave_types(rows) -> list[str]:
	"""Leave types shown as column groups: most employees with an allocation first, then by name."""
	counts = {}
	for row in rows:
		for leave_type in row["leave"]:
			counts[leave_type] = counts.get(leave_type, 0) + 1
	return sorted(counts, key=lambda leave_type: (-counts[leave_type], leave_type))


def _leave_dates(employees, sick_types, today) -> dict:
	"""Last and next approved leave and the open applications per employee, without sick leave."""
	if not employees:
		return {}
	application = frappe.qb.DocType("Leave Application")
	base = frappe.qb.from_(application).where(application.employee.isin(employees))
	if sick_types:
		base = base.where(application.leave_type.notin(sick_types))
	approved = base.where((application.docstatus == 1) & (application.status == "Approved"))
	result = {name: {"last_leave": None, "next_leave": None, "pending_count": 0} for name in employees}
	for employee, last_leave in (
		approved.select(application.employee, Max(application.to_date))
		.where(application.from_date <= today)
		.groupby(application.employee)
	).run():
		result[employee]["last_leave"] = last_leave
	for employee, next_leave in (
		approved.select(application.employee, Min(application.from_date))
		.where(application.from_date > today)
		.groupby(application.employee)
	).run():
		result[employee]["next_leave"] = next_leave
	for employee, pending in (
		base.select(application.employee, Count("*"))
		.where((application.docstatus == 0) & (application.status == "Open"))
		.groupby(application.employee)
	).run():
		result[employee]["pending_count"] = pending
	return result
