# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Hours statistics of a Team (#1975): logged against available hours, in hours only.

Available hours per member and day (decision 6 of #1954, #1975):
- scheduled hours from `team_capacity_utils.get_employee_scheduled_hours`: the submitted Weekly
  Working Hours valid that day, else the Employment Contract's weekly hours / 5 on Monday to Friday
- minus holidays (the employee's Holiday List, else the company's default) and approved leave
  (half day only on its date)
- only on days the person was in the team (Team Assignment, #1974)

A day without Weekly Working Hours and without a contract has unknown available hours. Rates use
only days with a known source on both sides; a member with no known day at all is named in
`missing_hours` (decision 4 of #1975). Their logged hours still count in the totals.

Logged hours (draft and submitted Timesheets of the member, not cancelled ones, by the day of
`from_time`, as the Team Capacity Overview and the Implementation count them) fall into three
groups (decision 3 of #1975):
- internal: the project's customer is an internal customer, or the project is marked
  "Is Internal Project", or the hour has no project
- billable: customer work with `is_billable`
- non_billable: other customer work

Every member is loaded once per page over the whole range (from 1 January of last year), as one
figure per day; the windows, months and years are sums over those days.
"""

from datetime import date, timedelta

import frappe
from frappe.utils import add_days, add_months, get_first_day, get_last_day, getdate

from phamos.phamos import team_capacity_utils as capacity
from phamos.phamos.doctype.team_assignment.team_assignment import members_between
from phamos.phamos.team_capacity_utils import LEAVE_FIELDS, leave_day_share

GROUPS = ("billable", "non_billable", "internal")


def _days(start, end):
	day = start
	while day <= end:
		yield day
		day += timedelta(days=1)


def _absences(employee, start, end):
	"""{date: share of the day absent} from holidays and approved leave in [start, end]. A holiday
	inside a leave counts once, as a holiday."""
	absent = {}
	holiday_list = capacity.employee_holiday_list(employee)
	if holiday_list:
		for day in frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [start, end]]},
			pluck="holiday_date",
		):
			absent[getdate(day)] = 1
	for leave in frappe.get_all(
		"Leave Application",
		filters={
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", end],
			"to_date": [">=", start],
		},
		fields=LEAVE_FIELDS,
	):
		for day in _days(max(getdate(leave.from_date), start), min(getdate(leave.to_date), end)):
			absent.setdefault(day, leave_day_share(leave, day))
	return absent


def hour_group(row):
	if not row.project or row.internal_project or row.internal_customer:
		return "internal"
	return "billable" if row.is_billable else "non_billable"


def _logged_by_day(employee, start, end):
	"""{date: {group: hours}} of `employee` in [start, end], one query."""
	project_internal = "p.custom_is_internal_project" if frappe.db.has_column("Project", "custom_is_internal_project") else "0"
	rows = frappe.db.sql(
		f"""
		select date(td.from_time) as day, td.is_billable, td.project,
			ifnull({project_internal}, 0) as internal_project,
			ifnull(c.is_internal_customer, 0) as internal_customer,
			sum(td.hours) as hours
		from `tabTimesheet Detail` td
		join `tabTimesheet` t on t.name = td.parent
		left join `tabProject` p on p.name = td.project
		left join `tabCustomer` c on c.name = p.customer
		where t.docstatus < 2 and t.employee = %(employee)s
			and td.from_time >= %(start)s and td.from_time < %(after_end)s
		group by 1, 2, 3, 4, 5
		""",
		{"employee": employee, "start": start, "after_end": add_days(end, 1)},
		as_dict=True,
	)
	logged = {}
	for row in rows:
		day = logged.setdefault(getdate(row.day), dict.fromkeys(GROUPS, 0.0))
		day[hour_group(row)] += row.hours or 0
	return logged


def member_days(employee, periods):
	"""{date: frappe._dict(available, known, fte, billable, non_billable, internal)} for the days of
	`periods` [(start, end), ...]: the days the person was in the team."""
	days = {}
	for start, end in periods:
		absent = _absences(employee, start, end)
		logged = _logged_by_day(employee, start, end)
		for day in _days(start, end):
			hours, source = capacity.get_employee_scheduled_hours(employee, day)
			contract = capacity._contract_on(employee, day)
			days[day] = frappe._dict(
				available=hours * (1 - absent.get(day, 0)),
				known=bool(source),
				fte=(contract.fte_percentage or 0) / 100 if contract else 0,
				**logged.get(day, dict.fromkeys(GROUPS, 0.0)),
			)
	return days


def available_hours(employee, periods):
	"""(hours, known) over `periods`; known is False when no day has a source."""
	days = member_days(employee, periods).values()
	return sum(d.available for d in days if d.known), any(d.known for d in days)


def member_row(employee, employee_name, days, start, end):
	"""One member's figures for [start, end] from their days in the team, or None if they were not
	in the team on any of those days."""
	in_range = [d for day, d in days.items() if start <= day <= end]
	if not in_range:
		return None
	known = [d for d in in_range if d.known]
	available = sum(d.available for d in known)
	logged = {group: sum(d[group] for d in in_range) for group in GROUPS}
	logged_known = sum(sum(d[group] for group in GROUPS) for d in known)
	billable_known = sum(d.billable for d in known)
	return frappe._dict(
		employee=employee,
		employee_name=employee_name,
		known=bool(known),
		available=round(available, 1) if known else None,
		logged=round(sum(logged.values()), 1),
		**{group: round(hours, 1) for group, hours in logged.items()},
		# rates only over days with known working hours, on both sides
		available_known=available,
		logged_known=logged_known,
		billable_known=billable_known,
		booked_rate=round(logged_known / available * 100, 1) if available else None,
		billable_rate=round(billable_known / available * 100, 1) if available else None,
		# FTE-days, and the hours logged on days with a contract FTE
		fte_days=sum(d.fte for d in in_range),
		logged_with_fte=sum(sum(d[group] for group in GROUPS) for d in in_range if d.fte),
	)


def totals(rows, period_days):
	"""Team figures for a period of `period_days` calendar days."""
	available = sum(r.available_known for r in rows)
	fte_total = sum(r.fte_days for r in rows) / period_days if period_days else 0
	return frappe._dict(
		logged=round(sum(r.logged for r in rows), 1),
		available=round(available, 1),
		booked_rate=round(sum(r.logged_known for r in rows) / available * 100, 1) if available else None,
		billable_rate=round(sum(r.billable_known for r in rows) / available * 100, 1) if available else None,
		# someone in the team for a fifth of the period counts as a fifth of their FTE
		fte=round(fte_total, 2),
		hours_per_fte=round(sum(r.logged_with_fte for r in rows) / fte_total, 1) if fte_total else None,
		**{group: round(sum(r[group] for r in rows), 1) for group in GROUPS},
	)


def month_windows(today=None):
	"""This month to date, the previous month to the same day, and the same month last year to the
	same day: so a comparison never sets part of a month against a whole one."""
	today = getdate(today)
	first = get_first_day(today)
	previous_first = get_first_day(add_months(first, -1))
	last_year_first = get_first_day(add_months(first, -12))

	def to_same_day(month_first):
		return min(month_first + (today - first), getdate(get_last_day(month_first)))

	return {
		"current": (first, today),
		"previous": (previous_first, to_same_day(previous_first)),
		"last_year": (last_year_first, to_same_day(last_year_first)),
	}


def same_day_last_year(today):
	try:
		return today.replace(year=today.year - 1)
	except ValueError:  # 29 February
		return date(today.year - 1, 2, 28)


def team_statistics(team, today=None):
	"""Everything the Statistics page shows, unfiltered (the API filters the member rows).

	Dates go out as ISO dates; the page formats them in the user's language. Only the current
	window carries member rows.
	"""
	today = getdate(today)
	range_start = date(today.year - 1, 1, 1)
	people = []
	for employee, periods in members_between(team, range_start, today).items():
		name = frappe.db.get_value("Employee", employee, "employee_name") or employee
		people.append((employee, name, member_days(employee, periods)))
	people.sort(key=lambda p: p[1])

	def stats(start, end):
		rows = [member_row(employee, name, days, start, end) for employee, name, days in people]
		rows = [r for r in rows if r]
		return rows, totals(rows, (end - start).days + 1)

	windows = {}
	for key, (start, end) in month_windows(today).items():
		rows, period_totals = stats(start, end)
		windows[key] = frappe._dict(start=start, end=end, totals=period_totals, members=rows if key == "current" else [])

	months = []
	for offset in range(11, -1, -1):
		start = get_first_day(add_months(today, -offset))
		month_end = getdate(get_last_day(start))
		end = min(month_end, today)
		months.append(frappe._dict(start=start, end=end, totals=stats(start, end)[1], mtd=end < month_end))

	current_rows = windows["current"].members
	return frappe._dict(
		today=today,
		windows=windows,
		months=months,
		year=frappe._dict(
			current=stats(date(today.year, 1, 1), today)[1],
			last_year=stats(date(today.year - 1, 1, 1), same_day_last_year(today))[1],
		),
		missing_hours=[{"employee": r.employee, "employee_name": r.employee_name} for r in current_rows if not r.known],
	)
