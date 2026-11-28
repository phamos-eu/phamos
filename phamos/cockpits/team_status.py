# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team mates and their status today (#1978), derived, never kept by hand.

Per person in the team today (Team Assignment, #1974):
- presence, the first that applies: absent (approved leave; the leave type is not shown, #1720),
  holiday (public holiday) or day off (weekly off), checked in since hh:mm, not checked in
- in focus: an active Focus Session that has not run past its limit
- timer: the project and task of a running or paused timer (decision 1 of #1978); no durations

Running timer: the employee's newest draft Timesheet Record, created within the last two days
(older drafts are left-overs, not timers), its last row open; an even row count is work, odd is a
break (as dev_action_panel reads it).

Live updates (decision 2): `publish_member_status(employee)` sends the person's new row to
everyone in their team, from the check-in, timer and focus hooks.
"""

import frappe
from frappe.utils import add_days, get_datetime, getdate, now_datetime

from phamos.cockpits import teams
from phamos.phamos.doctype.team_assignment.team_assignment import members_of
from phamos.phamos.team_capacity_utils import employee_holiday_list

EVENT = "team_member_status"
TIMER_MAX_AGE_DAYS = 2


def _presence(employee, now):
	today = getdate(now)
	if frappe.db.exists(
		"Leave Application",
		{
			"employee": employee,
			"docstatus": 1,
			"status": "Approved",
			"from_date": ["<=", today],
			"to_date": [">=", today],
		},
	):
		return {"presence": "absent"}
	holiday_list = employee_holiday_list(employee)
	if holiday_list:
		weekly_off = frappe.db.get_value("Holiday", {"parent": holiday_list, "holiday_date": today}, "weekly_off")
		if weekly_off is not None:
			return {"presence": "day_off" if weekly_off else "holiday"}
	last = frappe.get_all(
		"Employee Checkin",
		filters={"employee": employee},
		fields=["log_type", "time"],
		order_by="time desc, creation desc",
		limit=1,
	)
	if last and last[0].log_type == "IN" and getdate(last[0].time) == today:
		return {"presence": "checked_in", "since": get_datetime(last[0].time).strftime("%H:%M")}
	return {"presence": "not_checked_in"}


def _in_focus(user, now):
	if not user:
		return False
	from phamos.api.personal_focus import DOCTYPE, _session_end_limit

	session = frappe.get_all(
		DOCTYPE,
		filters={"user": user, "status": "Active"},
		fields=["planned_minutes", "planned_end", "started_at"],
		limit=1,
	)
	return bool(session) and _session_end_limit(session[0]) > get_datetime(now)


def _timer(employee, now):
	"""{project, project_name, task, task_subject, state} of the running or paused timer, or None."""
	records = frappe.get_all(
		"Timesheet Record",
		filters={"employee": employee, "docstatus": 0, "creation": [">=", add_days(now, -TIMER_MAX_AGE_DAYS)]},
		fields=["name", "project", "task"],
		order_by="creation desc",
		limit=1,
	)
	if not records:
		return None
	record = records[0]
	rows = frappe.get_all(
		"Timesheet Record Item", filters={"parent": record.name}, fields=["to_time"], order_by="idx asc"
	)
	if not rows or rows[-1].to_time:
		return None
	state = "running" if (len(rows) - 1) % 2 == 0 else "paused"
	return {
		"project": record.project,
		"project_name": frappe.db.get_value("Project", record.project, "project_name") if record.project else None,
		"task": record.task,
		"task_subject": frappe.db.get_value("Task", record.task, "subject") if record.task else None,
		"state": state,
	}


def status_row(employee, now=None):
	now = now or now_datetime()
	emp = frappe.db.get_value("Employee", employee, ["employee_name", "user_id", "image"], as_dict=True) or {}
	user = emp.get("user_id")
	return {
		"employee": employee,
		"employee_name": emp.get("employee_name") or employee,
		"user": user,
		"image": (frappe.db.get_value("User", user, "user_image") if user else None) or emp.get("image"),
		**_presence(employee, now),
		"focus": _in_focus(user, now),
		"timer": _timer(employee, now),
	}


def team_mates(team, now=None):
	"""Status rows of the team's people today, sorted by name."""
	now = now or now_datetime()
	rows = [status_row(employee, now) for employee in members_of(team, getdate(now))]
	return sorted(rows, key=lambda r: r["employee_name"])


def publish_member_status(employee):
	"""Send `employee`'s new status row to the people of their team(s)."""
	if not employee:
		return
	user = frappe.db.get_value("Employee", employee, "user_id")
	if not user:
		return
	row = None
	for team in teams.member_teams(user):
		row = row or status_row(employee)
		for recipient in teams.team_users(team):
			frappe.publish_realtime(EVENT, {"team": team, "row": row}, user=recipient["name"], after_commit=True)


def publish_quietly(employee):
	"""For the check-in, timer and focus hooks: a failing team update must not fail their save."""
	try:
		publish_member_status(employee)
	except Exception:
		frappe.log_error(title="Team mate status not published")
