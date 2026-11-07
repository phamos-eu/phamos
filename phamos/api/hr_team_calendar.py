# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Calendar in the Human Resources Cockpit (phamos/phamos#1838).

Who is away when, for the whole team, in one month:
- Absences are neutral for every role (Decision 3): the answer carries no leave type and no
  reason, so sick leave and annual leave look the same and nobody learns why someone is away.
- Approved leave and open requests (Decision 4); rejected and cancelled ones never became an
  absence and are left out.
- Birthdays as dates inside the range; the year of birth never leaves the server (#1833).
- Holidays per Holiday List with the list's country code, for the flag (Decision 6). Weekly offs
  come separately, so the page can shade them without calling them holidays.
- Same roles as the Employees list; employees through `get_list`, so User Permissions apply.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import getdate, strip_html

from phamos.api.hr_employees import _check_access

# A month view asks for about six weeks; a year is the most any view needs.
MAX_DAYS = 400


@frappe.whitelist()
def get_team_calendar(from_date: str, to_date: str, company: str | None = None) -> dict:
	"""Active employees with their absences, birthdays and holidays between the two dates."""
	_check_access()
	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(_("The end date must not be before the start date."))
	if (end - start).days > MAX_DAYS:
		frappe.throw(_("The calendar shows at most {0} days at once.").format(MAX_DAYS))

	filters = {"status": "Active"}
	if company:
		filters["company"] = company
	employees = frappe.get_list(
		"Employee",
		filters=filters,
		fields=["name", "employee_name", "image", "user_id", "company", "holiday_list", "date_of_birth"],
		order_by="employee_name asc",
		limit_page_length=0,
	)
	names = [e.name for e in employees]
	user_images = _user_images([e.user_id for e in employees if e.user_id and not e.image])

	return {
		"from_date": start,
		"to_date": end,
		"employees": [
			{
				"employee": e.name,
				"employee_name": e.employee_name,
				"image": e.image or user_images.get(e.user_id),
				"company": e.company,
				"holiday_list": e.holiday_list,
			}
			for e in employees
		],
		"absences": _absences(names, start, end),
		"birthdays": [
			{"employee": e.name, "date": day}
			for e in employees
			if e.date_of_birth
			for day in _birthdays_between(getdate(e.date_of_birth), start, end)
		],
		"holiday_lists": _holiday_lists({e.holiday_list for e in employees if e.holiday_list}, start, end),
		"companies": frappe.get_all("Company", pluck="name", order_by="name asc"),
	}


def _user_images(users: list[str]) -> dict:
	if not users:
		return {}
	return dict(frappe.get_all("User", filters={"name": ("in", users)}, fields=["name", "user_image"], as_list=True))


def _absences(employees: list[str], start, end) -> list[dict]:
	"""Approved leave and open requests overlapping the range. No leave type, no reason."""
	if not employees:
		return []
	application = frappe.qb.DocType("Leave Application")
	approved = (application.docstatus == 1) & (application.status == "Approved")
	requested = (application.docstatus == 0) & (application.status == "Open")
	rows = (
		frappe.qb.from_(application)
		.select(
			application.employee,
			application.from_date,
			application.to_date,
			application.half_day,
			application.half_day_date,
			application.docstatus,
		)
		.where(application.employee.isin(employees))
		.where(application.from_date <= end)
		.where(application.to_date >= start)
		.where(approved | requested)
		.orderby(application.from_date)
	).run(as_dict=True)
	return [
		{
			"employee": row.employee,
			"from_date": row.from_date,
			"to_date": row.to_date,
			"half_day": bool(row.half_day),
			"half_day_date": row.half_day_date,
			"requested": row.docstatus == 0,
		}
		for row in rows
	]


def _birthdays_between(date_of_birth: datetime.date, start, end) -> list[datetime.date]:
	"""Each birthday inside the range; 29 February falls on the 28th in other years."""
	days = []
	for year in range(start.year, end.year + 1):
		day = date_of_birth.day
		if date_of_birth.month == 2 and day == 29 and not calendar.isleap(year):
			day = 28
		birthday = datetime.date(year, date_of_birth.month, day)
		if start <= birthday <= end:
			days.append(birthday)
	return days


def _holiday_lists(names: set[str], start, end) -> dict:
	"""Per Holiday List: country code for the flag, holidays, and weekly offs apart."""
	if not names:
		return {}
	lists = frappe.get_all(
		"Holiday List", filters={"name": ("in", list(names))}, fields=["name", "country", "subdivision"]
	)
	codes = dict(
		frappe.get_all(
			"Country",
			filters={"name": ("in", [h.country for h in lists if h.country])},
			fields=["name", "code"],
			as_list=True,
		)
	)
	result = {
		h.name: {
			"country": h.country,
			"country_code": (codes.get(h.country) or "").upper() or None,
			"subdivision": h.subdivision,
			"holidays": [],
			"weekly_offs": [],
		}
		for h in lists
	}
	for row in frappe.get_all(
		"Holiday",
		filters={"parent": ("in", list(result)), "parenttype": "Holiday List", "holiday_date": ("between", [start, end])},
		fields=["parent", "holiday_date", "description", "weekly_off"],
		order_by="holiday_date asc",
	):
		if row.weekly_off:
			result[row.parent]["weekly_offs"].append(row.holiday_date)
		else:
			result[row.parent]["holidays"].append(
				{"date": row.holiday_date, "description": strip_html(row.description or "").strip()}
			)
	return result
