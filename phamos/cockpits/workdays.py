# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Working days of a user for the Personal Cockpit (#1555, reused by challenges #1557).

A day is not a working day when it is a Saturday or Sunday, a holiday in the user's
Employee holiday list (or the company default), or covered by an approved Leave
Application. Users without an Employee record only skip weekends. Every source is
optional: ERPNext and HRMS may be missing on a site.
"""

from datetime import timedelta

import frappe
from frappe.utils import getdate

WEEKEND = (5, 6)  # Saturday, Sunday
# Bound for searches, so a holiday list covering everything cannot loop forever.
MAX_SEARCH_DAYS = 60


def _employee(user):
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def _holiday_list(employee):
	try:
		from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee
	except ImportError:
		return None
	return get_holiday_list_for_employee(employee, raise_exception=False)


def days_off(user, start, end):
	"""Holidays and approved leave of `user` between `start` and `end` (inclusive), as dates."""
	start, end = getdate(start), getdate(end)
	employee = _employee(user)
	if not employee:
		return set()

	off = set()
	holiday_list = _holiday_list(employee)
	if holiday_list:
		off.update(
			getdate(day)
			for day in frappe.get_all(
				"Holiday",
				filters={"parent": holiday_list, "holiday_date": ("between", (start, end))},
				pluck="holiday_date",
			)
		)

	if frappe.db.exists("DocType", "Leave Application"):
		for leave in frappe.get_all(
			"Leave Application",
			filters={
				"employee": employee,
				"status": "Approved",
				"docstatus": 1,
				"from_date": ("<=", end),
				"to_date": (">=", start),
			},
			fields=["from_date", "to_date"],
		):
			day = max(getdate(leave.from_date), start)
			while day <= min(getdate(leave.to_date), end):
				off.add(day)
				day += timedelta(days=1)
	return off


def is_working_day(day, off=frozenset()):
	day = getdate(day)
	return day.weekday() not in WEEKEND and day not in off


def add_working_days(start, count, user=None):
	"""The date `count` working days after `start` (0 = `start` itself, or the next working day)."""
	start = getdate(start)
	user = user or frappe.session.user
	off = days_off(user, start, start + timedelta(days=MAX_SEARCH_DAYS + count * 2))
	day = start
	while not is_working_day(day, off) and (day - start).days < MAX_SEARCH_DAYS:
		day += timedelta(days=1)
	remaining = count
	while remaining > 0 and (day - start).days < MAX_SEARCH_DAYS + count * 2:
		day += timedelta(days=1)
		if is_working_day(day, off):
			remaining -= 1
	return day
