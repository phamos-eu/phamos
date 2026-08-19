# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_months, getdate


def execute(filters=None):
	if not filters:
		filters = {}

	columns = get_columns()
	data = get_employees(filters)

	return columns, data


def get_columns():
	return [
		{"label": _("Employee"), "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 120},
		{"label": _("Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
		{"label": _("Date of Birth"), "fieldname": "date_of_birth", "fieldtype": "Date", "width": 100},
		{"label": _("Next Birthday"), "fieldname": "next_birthday", "fieldtype": "Date", "width": 100},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 120},
		{"label": _("Department"), "fieldname": "department", "fieldtype": "Link", "options": "Department", "width": 120},
		{"label": _("Designation"), "fieldname": "designation", "fieldtype": "Link", "options": "Designation", "width": 120},
		{"label": _("Gender"), "fieldname": "gender", "fieldtype": "Data", "width": 60},
		{"label": _("Company"), "fieldname": "company", "fieldtype": "Link", "options": "Company", "width": 120},
	]


def get_employees(filters):
	conditions = {"status": "Active", "date_of_birth": ["is", "set"]}
	if filters.get("company"):
		conditions["company"] = filters["company"]

	employees = frappe.get_all(
		"Employee",
		filters=conditions,
		fields=[
			"name as employee",
			"employee_name",
			"date_of_birth",
			"branch",
			"department",
			"designation",
			"gender",
			"company",
		],
	)

	today = getdate()
	window_end = add_months(today, 1)

	upcoming = []
	for emp in employees:
		next_birthday = get_next_birthday(getdate(emp.date_of_birth), today)
		if today <= next_birthday <= window_end:
			emp["next_birthday"] = next_birthday
			upcoming.append(emp)

	upcoming.sort(key=lambda row: row["next_birthday"])
	return upcoming


def get_next_birthday(date_of_birth, today):
	"""Return the next occurrence (this year or next) of date_of_birth on/after today.

	Falls back to Feb 28 for Feb 29 birthdays in non-leap years so the report
	doesn't skip a year for people born on a leap day.
	"""
	next_birthday = safe_replace_year(date_of_birth, today.year)
	if next_birthday < today:
		next_birthday = safe_replace_year(date_of_birth, today.year + 1)
	return next_birthday


def safe_replace_year(date_of_birth, year):
	try:
		return date_of_birth.replace(year=year)
	except ValueError:
		# Feb 29 in a non-leap target year
		return date_of_birth.replace(year=year, day=28)
