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

Coverage (PM, 2026-11-08): how much of the team is available, as person-days available out of
person-days expected to work. Weekends, weekly offs and holidays of each employee's Holiday List
are not expected days; a half day counts half. Upcoming weeks count approved leave and open
requests as away (a forecast should not look better than it is); the average is the last twelve
months with approved leave only, counting each employee only while employed.
"""

from __future__ import annotations

import calendar
import datetime

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, strip_html
from frappe.utils.data import get_start_of_week_index

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


COVERAGE_WEEKS = 4
AVERAGE_DAYS = 365


def _today() -> datetime.date:
	return getdate(nowdate())


@frappe.whitelist()
def get_coverage(company: str | None = None) -> dict:
	"""Coverage of this week and the next three, and the average of the last twelve months."""
	_check_access()
	today = _today()
	# Python counts Monday as 0, Frappe's week index Sunday as 0.
	week_start = add_days(today, -((today.weekday() - (get_start_of_week_index() - 1)) % 7))
	filters = {"company": company} if company else {}
	employees = frappe.get_list(
		"Employee",
		filters=filters,
		fields=["name", "company", "holiday_list", "date_of_joining", "relieving_date", "status"],
		limit_page_length=0,
	)
	weeks = []
	for index in range(COVERAGE_WEEKS):
		start = add_days(week_start, index * 7)
		end = add_days(start, 6)
		weeks.append({"start": start, "end": end, **_coverage(employees, start, end, with_requests=True)})
	average = _coverage(employees, add_days(today, -AVERAGE_DAYS), add_days(today, -1), with_requests=False)
	return {"weeks": weeks, "average": average, "average_from": add_days(today, -AVERAGE_DAYS)}


def _coverage(employees, start, end, with_requests: bool) -> dict:
	"""Person-days expected and available between two dates, and the share in percent (None if none expected)."""
	off_days = _off_days(employees, start, end)
	away = _away_days([e.name for e in employees], start, end, with_requests)
	expected = available = 0.0
	day = start
	while day <= end:
		for employee in employees:
			if not _employed(employee, day) or day in off_days.get(employee.name, ()):
				continue
			expected += 1
			available += 1 - away.get((employee.name, day), 0)
		day = add_days(day, 1)
	return {
		"expected": expected,
		"available": available,
		"coverage": round(100 * available / expected, 1) if expected else None,
	}


def _employed(employee, day) -> bool:
	if employee.date_of_joining and getdate(employee.date_of_joining) > day:
		return False
	if employee.relieving_date and getdate(employee.relieving_date) < day:
		return False
	# Without a relieving date a former employee's last day is unknown; count only active ones then.
	return employee.status == "Active" or bool(employee.relieving_date)


def _off_days(employees, start, end) -> dict:
	"""employee → dates not expected to work: holidays and weekly offs, else Saturday and Sunday."""
	company_lists = dict(
		frappe.get_all("Company", fields=["name", "default_holiday_list"], as_list=True)
	)
	list_of = {e.name: e.holiday_list or company_lists.get(e.company) for e in employees}
	dates = {}
	for row in frappe.get_all(
		"Holiday",
		filters={
			"parent": ("in", [name for name in set(list_of.values()) if name] or [""]),
			"parenttype": "Holiday List",
			"holiday_date": ("between", [start, end]),
		},
		fields=["parent", "holiday_date", "weekly_off"],
	):
		entry = dates.setdefault(row.parent, {"days": set(), "weekly_offs": False})
		entry["days"].add(getdate(row.holiday_date))
		entry["weekly_offs"] |= bool(row.weekly_off)
	weekend = set()
	day = start
	while day <= end:
		if day.weekday() >= 5:
			weekend.add(day)
		day = add_days(day, 1)
	result = {}
	for employee, holiday_list in list_of.items():
		entry = dates.get(holiday_list, {"days": set(), "weekly_offs": False})
		# A list without weekly offs (only public holidays) still has free weekends.
		result[employee] = entry["days"] if entry["weekly_offs"] else entry["days"] | weekend
	return result


def _away_days(employees: list[str], start, end, with_requests: bool) -> dict:
	"""(employee, date) → 1 or 0.5 for every day of leave in the range."""
	if not employees:
		return {}
	application = frappe.qb.DocType("Leave Application")
	condition = (application.docstatus == 1) & (application.status == "Approved")
	if with_requests:
		condition = condition | ((application.docstatus == 0) & (application.status == "Open"))
	rows = (
		frappe.qb.from_(application)
		.select(
			application.employee,
			application.from_date,
			application.to_date,
			application.half_day,
			application.half_day_date,
		)
		.where(application.employee.isin(employees))
		.where(application.from_date <= end)
		.where(application.to_date >= start)
		.where(condition)
	).run(as_dict=True)
	away = {}
	for row in rows:
		half = getdate(row.half_day_date or row.from_date) if row.half_day else None
		day = max(getdate(row.from_date), start)
		while day <= min(getdate(row.to_date), end):
			share = 0.5 if day == half else 1
			away[(row.employee, day)] = max(away.get((row.employee, day), 0), share)
			day = add_days(day, 1)
	return away
