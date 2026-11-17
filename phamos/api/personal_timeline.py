# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Day as a timeline (phamos/phamos#1573): what happened on each day, and what is planned.

For a range of days this returns, for the session user only:

- check-ins and check-outs (HRMS Employee Checkin of my Employee, when HRMS is installed);
- time logs: my Timesheet Records with their time rows (even rows are work, odd rows are breaks,
  as in the Action Panels); a running draft has an open last row;
- ToDos I closed, flagged when they were planned (#1561);
- the day plan with its outcome counts and the one-line reflection.

Time logs are returned once for the whole range; the client places their rows on the days they
touch. Datetimes are naive system-time-zone values like everywhere else in Frappe.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime

from phamos.api import personal_day_plan, personal_todos
from phamos.cockpits.workdays import _employee

MAX_DAYS = 31
CHECKIN = "Employee Checkin"
RECORD = "Timesheet Record"


def _range(from_date, to_date):
	start, end = getdate(from_date), getdate(to_date)
	if end < start:
		frappe.throw(_("The end of the range is before its start."))
	if (end - start).days + 1 > MAX_DAYS:
		frappe.throw(_("Load at most {0} days at a time.").format(MAX_DAYS))
	return start, end


def _bounds(start, end):
	return get_datetime(start), get_datetime(end + timedelta(days=1))


def _checkins(employee, low, high):
	if not employee or not frappe.db.exists("DocType", CHECKIN):
		return []
	return frappe.get_all(
		CHECKIN,
		filters={"employee": employee, "time": ("between", (low, high - timedelta(seconds=1)))},
		fields=["name", "log_type", "time", "device_id"],
		order_by="time asc",
	)


def _time_logs(employee, low, high):
	if not employee:
		return []
	# A record can start the day before and run into the range (left running overnight).
	records = frappe.get_all(
		RECORD,
		filters={
			"employee": employee,
			"docstatus": ("!=", 2),
			"from_time": ("between", (low - timedelta(days=1), high - timedelta(seconds=1))),
		},
		fields=["name", "docstatus", "project", "customer", "goal", "result", "activity_type", "percent_billable", "value_add", "task"],
		order_by="from_time asc",
	)
	if not records:
		return []
	rows = frappe.get_all(
		"Timesheet Record Item",
		filters={"parenttype": RECORD, "parent": ("in", [r.name for r in records])},
		fields=["parent", "idx", "from_time", "to_time"],
		order_by="parent asc, idx asc",
	)
	by_record = {}
	for row in rows:
		by_record.setdefault(row.parent, []).append(row)
	names = {
		row.name: row.project_name
		for row in frappe.get_all(
			"Project", filters={"name": ("in", list({r.project for r in records if r.project}))}, fields=["name", "project_name"]
		)
	}
	logs = []
	for record in records:
		segments = []
		for index, row in enumerate(by_record.get(record.name, [])):
			end = row.to_time
			if row.from_time and (end or record.docstatus == 0) and get_datetime(end or high) > low:
				segments.append({"from_time": row.from_time, "to_time": end, "kind": "work" if index % 2 == 0 else "break"})
		if segments:
			logs.append({**record, "project_name": names.get(record.project) or record.project, "segments": segments})
	return logs


def _todos_done(user, start, end, low, high):
	rows = frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": user,
			"cockpit_closed_by": user,
			"status": "Closed",
			"cockpit_closed_on": ("between", (low, high - timedelta(seconds=1))),
		},
		fields=["name", "description", "cockpit_closed_on", "cockpit_important"],
		order_by="cockpit_closed_on asc",
	)
	planned = personal_day_plan.planned_pairs(user, start, end)
	return [
		{
			"name": row.name,
			"summary": personal_todos._summary(row.description),
			"closed_on": row.cockpit_closed_on,
			"important": bool(row.cockpit_important),
			"planned": (getdate(row.cockpit_closed_on), row.name) in planned,
		}
		for row in rows
	]


def _plans(user, start, end):
	plans = {}
	for name in frappe.get_all(
		personal_day_plan.DOCTYPE, filters={"user": user, "date": ("between", (start, end))}, pluck="name"
	):
		doc = frappe.get_doc(personal_day_plan.DOCTYPE, name)
		counts = {"done": 0, "moved": 0, "dropped": 0, "open": 0}
		for item in personal_day_plan._serialize_items(doc):
			key = item["outcome"].lower()
			counts[key if key in counts else "open"] += 1
		plans[getdate(doc.date)] = {
			"status": doc.status,
			"confirmed_at": doc.confirmed_at,
			"shutdown_at": doc.shutdown_at,
			"reflection": doc.reflection or "",
			"counts": counts,
		}
	return plans


def _has_earlier(user, employee, low):
	if employee and frappe.db.exists("DocType", CHECKIN):
		if frappe.db.exists(CHECKIN, {"employee": employee, "time": ("<", low)}):
			return True
	if employee and frappe.db.exists(RECORD, {"employee": employee, "docstatus": ("!=", 2), "from_time": ("<", low)}):
		return True
	if frappe.db.exists("ToDo", {"cockpit_closed_by": user, "status": "Closed", "cockpit_closed_on": ("<", low)}):
		return True
	return bool(frappe.db.exists(personal_day_plan.DOCTYPE, {"user": user, "date": ("<", getdate(low))}))


def get_timeline(from_date, to_date):
	start, end = _range(from_date, to_date)
	low, high = _bounds(start, end)
	user = frappe.session.user
	employee = _employee(user)

	checkins = _checkins(employee, low, high)
	todos = _todos_done(user, start, end, low, high)
	plans = _plans(user, start, end)

	days = []
	day = start
	while day <= end:
		days.append(
			{
				"date": day,
				"checkins": [c for c in checkins if getdate(c.time) == day],
				"todos_done": [t for t in todos if getdate(t["closed_on"]) == day],
				"plan": plans.get(day),
			}
		)
		day += timedelta(days=1)

	return {
		"from_date": start,
		"to_date": end,
		"employee": employee,
		"days": days,
		"time_logs": _time_logs(employee, low, high),
		"has_earlier": _has_earlier(user, employee, low),
		"server_now": now_datetime(),
		"max_days": cint(MAX_DAYS),
	}
