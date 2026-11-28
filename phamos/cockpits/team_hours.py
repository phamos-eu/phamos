# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Hours statistics of a Team (#1975): logged against available hours, in hours only.

Available hours per member and day (decision 6 of #1954, #1975):
- scheduled hours from `team_capacity_utils.get_employee_scheduled_hours`: the submitted Weekly
  Working Hours valid that day, else the Employment Contract's weekly hours / 5 on Monday to Friday
- minus holidays of the employee's Holiday List and approved leave (half day only on its date)
- only on days the person was in the team (Team Assignment, #1974)

A member with neither Weekly Working Hours nor a contract in the period has unknown available
hours: they are left out of both sides of every rate, their logged hours still count in the
totals, and they are named in `missing_hours` (decision 4 of #1975).

Logged hours (draft and submitted Timesheets of the member, not cancelled ones, by the day of
`from_time`, as the Team Capacity Overview and the Implementation count them) fall into three
groups (decision 3 of #1975):
- internal: the project's customer is an internal customer, or the project is marked
  "Is Internal Project", or the hour has no project
- billable: customer work with `is_billable`
- non_billable: other customer work
"""

from datetime import date, timedelta

import frappe
from frappe.utils import add_months, get_first_day, get_last_day, getdate

from phamos.phamos.doctype.team_assignment.team_assignment import members_between
from phamos.phamos import team_capacity_utils as capacity
from phamos.phamos.team_capacity_utils import LEAVE_FIELDS, leave_day_share

GROUPS = ("billable", "non_billable", "internal")


def _days(start, end):
	day = start
	while day <= end:
		yield day
		day += timedelta(days=1)


def _absences(employee, start, end):
	"""{date: share of the day absent} from holidays and approved leave in [start, end]."""
	absent = {}
	holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
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


def available_hours(employee, periods):
	"""(hours, known) for `employee` over the date ranges `periods` [(start, end), ...].

	`known` is False when no day of the periods has Weekly Working Hours or a contract.
	"""
	total, known = 0.0, False
	for start, end in periods:
		absent = _absences(employee, start, end)
		for day in _days(start, end):
			hours, source = capacity.get_employee_scheduled_hours(employee, day)
			if source:
				known = True
			total += hours * (1 - absent.get(day, 0))
	return total, known


def fte(employee, periods):
	"""Average FTE (0..1) over the days of `periods`, from the contracts valid on each day."""
	days, weighted = 0, 0.0
	for start, end in periods:
		for day in _days(start, end):
			days += 1
			contract = capacity._contract_on(employee, day)
			weighted += (contract.fte_percentage or 0) / 100 if contract else 0
	return weighted / days if days else 0


def logged_hours(employee, periods):
	"""{group: hours} of `employee`'s submitted timesheet rows on the days of `periods`."""
	result = dict.fromkeys(GROUPS, 0.0)
	project_internal = "p.custom_is_internal_project" if frappe.db.has_column("Project", "custom_is_internal_project") else "0"
	for start, end in periods:
		rows = frappe.db.sql(
			f"""
			select td.hours, td.is_billable, td.project,
				ifnull({project_internal}, 0) as internal_project,
				ifnull(c.is_internal_customer, 0) as internal_customer
			from `tabTimesheet Detail` td
			join `tabTimesheet` t on t.name = td.parent
			left join `tabProject` p on p.name = td.project
			left join `tabCustomer` c on c.name = p.customer
			where t.docstatus < 2 and t.employee = %(employee)s
				and date(td.from_time) between %(start)s and %(end)s
			""",
			{"employee": employee, "start": start, "end": end},
			as_dict=True,
		)
		for row in rows:
			result[hour_group(row)] += row.hours or 0
	return result


def hour_group(row):
	if not row.project or row.internal_project or row.internal_customer:
		return "internal"
	return "billable" if row.is_billable else "non_billable"


def member_stats(team, start, end):
	"""One row per person in `team` during [start, end], each counted only for their days in it."""
	rows = []
	for employee, periods in members_between(team, start, end).items():
		available, known = available_hours(employee, periods)
		logged = logged_hours(employee, periods)
		rows.append(
			frappe._dict(
				employee=employee,
				employee_name=frappe.db.get_value("Employee", employee, "employee_name") or employee,
				available=round(available, 1) if known else None,
				known=known,
				fte=round(fte(employee, periods), 2),
				logged=round(sum(logged.values()), 1),
				**{group: round(hours, 1) for group, hours in logged.items()},
			)
		)
	return sorted(rows, key=lambda r: r.employee_name)


def totals(rows):
	"""Team figures from member rows. Rates use only members with known available hours."""
	known = [r for r in rows if r.known]
	available = sum(r.available for r in known)
	logged_known = sum(r.logged for r in known)
	billable_known = sum(r.billable for r in known)
	fte_total = sum(r.fte for r in rows)
	# only people with a contract FTE: dividing everyone's hours by part of the FTE would inflate it
	logged_with_fte = sum(r.logged for r in rows if r.fte)
	return frappe._dict(
		logged=round(sum(r.logged for r in rows), 1),
		available=round(available, 1),
		booked_rate=round(logged_known / available * 100, 1) if available else None,
		billable_rate=round(billable_known / available * 100, 1) if available else None,
		fte=round(fte_total, 2),
		hours_per_fte=round(logged_with_fte / fte_total, 1) if fte_total else None,
		**{group: round(sum(r[group] for r in rows), 1) for group in GROUPS},
	)


def period_stats(team, start, end, label):
	rows = member_stats(team, start, end)
	return frappe._dict(label=label, start=start, end=end, totals=totals(rows), members=rows)


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


def team_statistics(team, today=None):
	"""Everything the Statistics page shows, unfiltered (the API filters the member rows)."""
	today = getdate(today)
	windows = month_windows(today)
	result = frappe._dict(
		today=today,
		windows={
			key: period_stats(team, start, end, start.strftime("%b %Y")) for key, (start, end) in windows.items()
		},
	)
	months = []
	for offset in range(11, -1, -1):
		start = get_first_day(add_months(today, -offset))
		end = min(getdate(get_last_day(start)), today)
		stats = period_stats(team, start, end, start.strftime("%b %Y"))
		months.append(frappe._dict(label=stats.label, start=start, end=end, totals=stats.totals, mtd=end < getdate(get_last_day(start))))
	result.months = months
	year_start = date(today.year, 1, 1)
	last_year_start = date(today.year - 1, 1, 1)
	try:
		same_day_last_year = today.replace(year=today.year - 1)
	except ValueError:  # 29 February
		same_day_last_year = date(today.year - 1, 2, 28)
	result.year = frappe._dict(
		current=period_stats(team, year_start, today, str(today.year)).totals,
		last_year=period_stats(team, last_year_start, same_day_last_year, str(today.year - 1)).totals,
	)
	result.missing_hours = [
		{"employee": r.employee, "employee_name": r.employee_name}
		for r in result.windows["current"].members
		if not r.known
	]
	return result
