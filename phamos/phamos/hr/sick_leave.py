# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sick days from approved Leave Applications (phamos/phamos#1834).

Which Leave Types count as sick leave is a list in Phamos Settings (Human Resources Cockpit
tab), not a field on Leave Type: the PM wants no more custom fields on standard doctypes for
now (#1833, Decision 5). Sick days are health data (Art. 9 GDPR): callers decide who may see
them; this module only counts. The Personal Cockpit shows employees their own count, the
HR Cockpit shows other people's only to HR Manager (#1833, Decision 4).
"""

from __future__ import annotations

import datetime

import frappe
from frappe.utils import flt, getdate, nowdate

SETTINGS = "Phamos Settings"
SETTINGS_FIELD = "human_resources_sick_leave_types"


def get_sick_leave_types() -> list[str]:
	"""Leave Types configured as sick leave; empty while nothing is configured."""
	return frappe.get_all(
		"Sick Leave Type Item",
		filters={"parenttype": SETTINGS, "parent": SETTINGS, "parentfield": SETTINGS_FIELD},
		pluck="leave_type",
		order_by="idx asc",
	)


def year_bounds(on_date=None) -> tuple[datetime.date, datetime.date]:
	"""1 January and 31 December of the calendar year of `on_date` (default today)."""
	year = getdate(on_date or nowdate()).year
	return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def get_sick_days(employees, from_date, to_date) -> dict[str, float] | None:
	"""Sick days per employee in the period, or None while no sick leave type is configured.

	Counts approved, submitted Leave Applications of the configured types. An application
	that reaches outside the period is clipped to it, and the clipped part is counted by HRMS
	(`get_number_of_leave_days`), so holidays and half days follow the leave type's settings.
	One query for all employees.
	"""
	leave_types = get_sick_leave_types()
	if not leave_types:
		return None
	employees = [e for e in set(employees or []) if e]
	days = {employee: 0.0 for employee in employees}
	if not employees:
		return days

	from_date, to_date = getdate(from_date), getdate(to_date)
	applications = frappe.get_all(
		"Leave Application",
		filters={
			"employee": ("in", employees),
			"leave_type": ("in", leave_types),
			"docstatus": 1,
			"status": "Approved",
			"from_date": ("<=", to_date),
			"to_date": (">=", from_date),
		},
		fields=["employee", "leave_type", "from_date", "to_date", "half_day", "half_day_date", "total_leave_days"],
	)
	for row in applications:
		days[row.employee] += _days_in_period(row, from_date, to_date)
	return {employee: flt(value, 2) for employee, value in days.items()}


def _days_in_period(row, from_date, to_date) -> float:
	start, end = max(getdate(row.from_date), from_date), min(getdate(row.to_date), to_date)
	if start == getdate(row.from_date) and end == getdate(row.to_date):
		return flt(row.total_leave_days)

	from hrms.hr.doctype.leave_application.leave_application import get_number_of_leave_days

	half_day_date = getdate(row.half_day_date) if row.half_day and row.half_day_date else None
	in_period = bool(half_day_date and start <= half_day_date <= end)
	return flt(
		get_number_of_leave_days(
			row.employee,
			row.leave_type,
			start,
			end,
			half_day=1 if in_period else 0,
			half_day_date=half_day_date if in_period else None,
		)
	)
