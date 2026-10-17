# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issues and Tasks dashboards of the Personal Cockpit (phamos/phamos#1604).

"Mine" is the cockpit's assignment rule: Issues and Tasks referenced by a ToDo allocated to the
session user. Open numbers use open assignments (as the lists do). "Recently done" numbers also
look at closed assignments, because closing an Issue or Task usually closes its assignment.

My hours come from my submitted Timesheet Records (`actual_time`, the worked time without
breaks, which is also what goes into the ERPNext Timesheet). The running timer is not counted.

Not whitelisted here: the `personal_cockpit` wrappers are the only endpoints, as for the other
personal modules (#1610).
"""

from datetime import datetime, time, timedelta

import frappe
from frappe.utils import flt, get_first_day, get_first_day_of_week, getdate, now_datetime, today

from phamos.api import dashboard_metrics as dm
from phamos.cockpits.defaults import AGE_BUCKETS, OLDEST_LIMIT
from phamos.cockpits.workdays import _employee

ISSUE_DONE = ("Resolved", "Closed")
TASK_DONE = ("Completed", "Cancelled", "Template")
RECENT_DAYS = 7
DUE_SOON_DAYS = 7
EFFORT_LIMIT = 8


def _my_references(doctype, include_closed=False):
	"""Names of `doctype` records assigned to me (open assignments; closed ones too if asked)."""
	statuses = ("Open", "Closed") if include_closed else ("Open",)
	names = frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": frappe.session.user,
			"reference_type": doctype,
			"status": ("in", statuses),
		},
		pluck="reference_name",
		limit_page_length=0,
	)
	return sorted({name for name in names if name})


def _load(doctype, names, fields):
	if not names:
		return []
	return frappe.get_list(doctype, filters={"name": ("in", names)}, fields=fields, limit_page_length=0)


def _count_by(rows, key, order=None, empty_label="—"):
	counts = {}
	for row in rows:
		label = row.get(key) or empty_label
		counts[label] = counts.get(label, 0) + 1
	# Known labels in their order first; anything else (e.g. a custom status) follows, largest
	# first, so the bars always add up to the total (#1609).
	known = [label for label in (order or []) if counts.get(label)]
	rest = sorted((label for label in counts if label not in known), key=lambda label: -counts[label])
	return [{"label": label, "value": counts[label]} for label in known + rest]


def _days_since(value, day):
	return (day - getdate(value)).days if value else None


def get_issue_dashboard():
	"""Numbers about my Issues: what waits on me, what waits on others, how old the open ones are."""
	day = getdate(today())
	fields = ["name", "subject", "status", "priority", "opening_date", "creation", "modified"]
	open_rows = [
		row
		for row in _load("Issue", _my_references("Issue"), fields)
		if row.status not in ISSUE_DONE
	]
	since = now_datetime() - timedelta(days=RECENT_DAYS)
	# There is no resolution date on Issue here; the last change of a resolved Issue stands in.
	resolved = [
		row
		for row in _load("Issue", _my_references("Issue", include_closed=True), fields)
		if row.status in ISSUE_DONE and row.modified and row.modified >= since
	]
	for row in open_rows:
		row.age_days = _days_since(row.opening_date or row.creation, day)
	oldest = sorted(open_rows, key=lambda row: -(row.age_days or 0))[:OLDEST_LIMIT]
	return {
		"totals": {
			"open": len(open_rows),
			"waiting_on_me": sum(1 for row in open_rows if row.status == "Open"),
			"waiting_on_others": sum(1 for row in open_rows if row.status in ("Replied", "On Hold")),
			"resolved_recently": len(resolved),
			"oldest_days": oldest[0].age_days if oldest else None,
		},
		"recent_days": RECENT_DAYS,
		"by_status": _count_by(open_rows, "status", order=["Open", "Replied", "On Hold"]),
		"by_priority": _count_by(open_rows, "priority", empty_label="No priority"),
		"by_age": dm.age_buckets(
			[{"start": row.opening_date or row.creation} for row in open_rows],
			datetime.combine(day, time.max),
			AGE_BUCKETS,
			created_field="start",
		),
		"oldest": [
			{"name": row.name, "subject": row.subject, "status": row.status, "age_days": row.age_days}
			for row in oldest
		],
	}


def _hours(employee, start):
	"""My worked hours per day since `start` (submitted Timesheet Records)."""
	if not employee:
		return {}
	# Own records only (filtered on my employee), so get_all is safe; get_list would depend on how
	# HR set up User Permissions for Timesheet Record.
	rows = frappe.get_all(
		"Timesheet Record",
		filters={"employee": employee, "docstatus": 1, "from_time": (">=", start)},
		fields=["from_time", "actual_time"],
		limit_page_length=0,
	)
	per_day = {}
	for row in rows:
		key = getdate(row.from_time)
		per_day[key] = per_day.get(key, 0) + flt(row.actual_time) / 3600
	return per_day


def _my_hours(day):
	employee = _employee(frappe.session.user)
	if not employee:
		return None
	week_start = getdate(get_first_day_of_week(day))
	month_start = getdate(get_first_day(day))
	per_day = _hours(employee, datetime.combine(min(week_start, month_start), time.min))
	total = lambda since: round(sum(hours for key, hours in per_day.items() if key >= since), 2)  # noqa: E731
	return {"today": total(day), "week": total(week_start), "month": total(month_start)}


def get_task_dashboard():
	"""Numbers about my Tasks: what is overdue or due soon, what I finished, my hours, effort vs plan."""
	day = getdate(today())
	fields = [
		"name",
		"subject",
		"status",
		"priority",
		"exp_end_date",
		"completed_on",
		"expected_time",
		"actual_time",
	]
	open_rows = [row for row in _load("Task", _my_references("Task"), fields) if row.status not in TASK_DONE]
	since = day - timedelta(days=RECENT_DAYS)
	completed = [
		row
		for row in _load("Task", _my_references("Task", include_closed=True), fields)
		if row.status == "Completed" and row.completed_on and getdate(row.completed_on) > since
	]
	soon_end = day + timedelta(days=DUE_SOON_DAYS)
	overdue = [row for row in open_rows if row.exp_end_date and getdate(row.exp_end_date) < day]
	due_soon = [row for row in open_rows if row.exp_end_date and day <= getdate(row.exp_end_date) <= soon_end]
	next_due = sorted(
		(row for row in open_rows if row.exp_end_date),
		key=lambda row: getdate(row.exp_end_date),
	)[:OLDEST_LIMIT]
	# Effort against the plan: open Tasks with an expected time, most used first.
	effort = sorted(
		(
			{
				"name": row.name,
				"label": row.subject or row.name,
				"actual": round(flt(row.actual_time), 2),
				"expected": round(flt(row.expected_time), 2),
				"value": round(flt(row.actual_time) / flt(row.expected_time) * 100),
				"theme": "red" if flt(row.actual_time) > flt(row.expected_time) else "blue",
			}
			for row in open_rows
			if flt(row.expected_time) > 0
		),
		key=lambda row: -row["value"],
	)[:EFFORT_LIMIT]
	return {
		"totals": {
			"open": len(open_rows),
			"overdue": len(overdue),
			"due_soon": len(due_soon),
			"completed_recently": len(completed),
		},
		"recent_days": RECENT_DAYS,
		"due_soon_days": DUE_SOON_DAYS,
		"hours": _my_hours(day),
		"by_status": _count_by(open_rows, "status", order=["Open", "Working", "Pending Review", "Overdue"]),
		"next_due": [
			{
				"name": row.name,
				"subject": row.subject,
				"exp_end_date": row.exp_end_date,
				"overdue": getdate(row.exp_end_date) < day,
			}
			for row in next_due
		],
		"effort": effort,
	}
