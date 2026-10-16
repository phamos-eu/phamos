# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Timesheet timer of the Personal Cockpit (phamos/phamos#1572).

The process is the one of the Developer and Project Action Panels: a running timer is a draft
Timesheet Record whose last item row is open; rows alternate work and break; Stop submits the
record, which creates the ERPNext Timesheet. This module does not reimplement any of it. It
delegates to the panel functions in `dev_action_panel.py` and adds what the Personal Cockpit
needs on top:

- every call that names a record first checks that the record belongs to my Employee (the
  panel functions do not, see #1549);
- one state call for the top bar (running, paused, waiting for a time-limit decision, or blocked
  by an empty draft);
- the project picker data (my projects, recent ones, search) and the project's task rule.
"""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from phamos.phamos.doctype.timesheet_record.timesheet_record import (
	compute_time_limit_status,
	notify_pm_of_time_limit,
	submit_at_available_hours,
)
from phamos.phamos.page.dev_action_panel import dev_action_panel as dap

DOCTYPE = "Timesheet Record"
MIN_EXPECTED_SECONDS = 15 * 60
RECENT_PROJECTS = 5
TASK_RULE_FIELD = "task_in_timesheet_record"
TASK_HIDDEN, TASK_OPTIONAL, TASK_MANDATORY = "Task is hidden", "Task is optional", "Task is mandatory"
BILLABLE_OPTIONS = ("0", "25", "50", "75", "100")


# who and what


def _my_employee():
	return frappe.db.get_value(
		"Employee",
		{"user_id": frappe.session.user, "status": "Active"},
		["name", "employee_name", "activity_type"],
		as_dict=True,
	)


def _require_employee():
	employee = _my_employee()
	if not employee:
		frappe.throw(_("Your user is not linked to an active Employee."))
	return employee


def _own_record(name):
	"""The Timesheet Record, if it belongs to my Employee (Administrator may act on any)."""
	doc = frappe.get_doc(DOCTYPE, name)
	if frappe.session.user != "Administrator":
		employee = _require_employee()
		if doc.employee != employee.name:
			frappe.throw(_("This timesheet record is not yours."), frappe.PermissionError)
	return doc


# state


def _session():
	"""The running or paused session, from the same detectors the Developer Action Panel uses."""
	user = frappe.session.user
	candidates = [s for s in (dap.get_active_project_session(), dap._get_active_session_raw(user)) if s]
	if not candidates:
		return None
	session = max(candidates, key=lambda s: get_datetime(s.get("from_time")))
	doc = frappe.get_doc(DOCTYPE, session["name"])
	rows = list(doc.item)
	state = session["session_state"]
	limit = None
	if rows and all(row.to_time for row in rows) and doc.result:
		# A stop that ran into the implementation's time limit: saved, not submitted.
		state = "limit_exceeded"
		limit = compute_time_limit_status(doc)
	project = frappe.db.get_value(
		"Project", doc.project, ["project_name", "percent_billable"], as_dict=True
	) or frappe._dict()
	return {
		"name": doc.name,
		"kind": "issue" if doc.gitlab_issue else "project",
		"state": state,
		"elapsed_seconds": cint(session.get("elapsed_seconds")),
		"break_from": session.get("break_from"),
		"from_time": doc.from_time,
		"open_row_from": next((row.from_time for row in reversed(rows) if not row.to_time), None),
		"project": doc.project,
		"project_name": project.get("project_name") or doc.project,
		"project_percent_billable": project.get("percent_billable") or "100",
		"customer": doc.customer,
		"task": doc.task,
		"task_subject": frappe.db.get_value("Task", doc.task, "subject") if doc.task else None,
		"goal": doc.goal,
		"result": doc.result,
		"expected_time": cint(doc.expected_time),
		"activity_type": doc.activity_type,
		"gitlab_issue": doc.gitlab_issue,
		"gitlab_issue_title": frappe.db.get_value("GitLab Issue", doc.gitlab_issue, "title") if doc.gitlab_issue else None,
		"limit": limit,
		"desk_url": f"/app/timesheet-record/{doc.name}",
	}


def _blocking_drafts(employee):
	"""My drafts without any time row. The panels refuse to start while they exist but never
	show them as a session (legacy Project Action Panel and "Make Timesheet" drafts)."""
	drafts = frappe.get_all(
		DOCTYPE,
		filters={"employee": employee, "docstatus": 0},
		fields=["name", "project", "goal", "creation"],
		order_by="creation desc",
	)
	with_rows = set(
		frappe.get_all(
			"Timesheet Record Item",
			filters={"parenttype": DOCTYPE, "parent": ("in", [d.name for d in drafts] or [""])},
			pluck="parent",
		)
	)
	return [
		{**draft, "desk_url": f"/app/timesheet-record/{draft.name}"}
		for draft in drafts
		if draft.name not in with_rows
	]


def get_timer_state():
	employee = _my_employee()
	if not employee:
		return {"available": False, "employee": None, "session": None, "blocking_drafts": [], "can_start": False}
	session = _session()
	blocking = [] if session else _blocking_drafts(employee.name)
	return {
		"available": True,
		"employee": employee.name,
		"default_activity_type": employee.activity_type,
		"session": session,
		"blocking_drafts": blocking,
		"can_start": not session and not blocking,
		"server_now": now_datetime(),
	}


# picker data


def _project_rows(names):
	if not names:
		return []
	rows = frappe.get_all(
		"Project",
		filters={"name": ("in", list(names)), "status": "Open"},
		fields=["name", "project_name", "customer"],
	)
	by_name = {row.name: row for row in rows}
	return [by_name[name] for name in names if name in by_name]


def get_timer_options():
	employee = _require_employee()
	mine = [row["name"] for row in dap.get_dev_my_projects() if row.get("status") == "Open"]
	recent = []
	for project in frappe.get_all(
		DOCTYPE,
		filters={"employee": employee.name, "docstatus": 1},
		order_by="creation desc",
		pluck="project",
		limit=100,
	):
		if project and project not in recent:
			recent.append(project)
		if len(recent) == RECENT_PROJECTS:
			break
	return {
		"my_projects": _project_rows(mine),
		"recent_projects": _project_rows(recent),
		"activity_types": frappe.get_all("Activity Type", filters={"disabled": 0}, pluck="name", order_by="name asc"),
		"default_activity_type": employee.activity_type,
	}


def search_timer_projects(txt=""):
	txt = (txt or "").strip()
	filters = {"status": "Open"}
	or_filters = {"name": ("like", f"%{txt}%"), "project_name": ("like", f"%{txt}%")} if txt else None
	return frappe.get_all(
		"Project",
		filters=filters,
		or_filters=or_filters,
		fields=["name", "project_name", "customer"],
		order_by="project_name asc",
		limit=20,
	)


def _task_rule(project):
	if not frappe.get_meta("Project").has_field(TASK_RULE_FIELD):
		return TASK_HIDDEN
	return frappe.db.get_value("Project", project, TASK_RULE_FIELD) or TASK_HIDDEN


def get_timer_project_info(project):
	if not frappe.db.exists("Project", project):
		frappe.throw(_("Project {0} not found.").format(project))
	rule = _task_rule(project)
	tasks = []
	if rule != TASK_HIDDEN:
		tasks = frappe.get_all(
			"Task",
			filters={"project": project, "status": ("not in", ["Cancelled", "Template", "Completed"])},
			fields=["name", "subject"],
			order_by="modified desc",
			limit=200,
		)
	return {
		"project": project,
		"percent_billable": frappe.db.get_value("Project", project, "percent_billable") or "100",
		"task_rule": rule,
		"tasks": tasks,
	}


# actions


def start_timer(project, expected_seconds, goal, task=None, manual_start_time=None):
	_require_employee()
	if frappe.db.get_value("Project", project, "status") != "Open":
		frappe.throw(_("Please pick an open project."))
	goal = (goal or "").strip()
	if not goal:
		frappe.throw(_("Please describe the goal of this session."))
	expected_seconds = cint(expected_seconds)
	if expected_seconds < MIN_EXPECTED_SECONDS:
		frappe.throw(_("Minimum expected time is 15 minutes."))

	rule = _task_rule(project)
	task = task or None
	if rule == TASK_HIDDEN:
		task = None
	elif rule == TASK_MANDATORY and not task:
		frappe.throw(_("This project needs a task for every timesheet record."))
	if task and frappe.db.get_value("Task", task, "project") != project:
		frappe.throw(_("Task {0} does not belong to project {1}.").format(task, project))

	started = dap.start_project_timer(project, expected_seconds, goal, manual_start_time=manual_start_time or None)
	if task:
		frappe.db.set_value(DOCTYPE, started["name"], "task", task)
	return get_timer_state()


def pause_timer(name):
	_own_record(name)
	dap.pause_timer(name)
	return get_timer_state()


def resume_timer(name, break_project=None, break_goal=None, break_result=None, break_activity_type=None, break_percent_billable=0):
	"""Resume; with break details the break is first logged as its own submitted record."""
	doc = _own_record(name)
	if break_project:
		break_from = next((row.from_time for row in reversed(doc.item) if not row.to_time), None)
		if not break_from:
			frappe.throw(_("There is no open break to log."))
		if not ((break_goal or "").strip() and (break_result or "").strip()):
			frappe.throw(_("Please describe the break's goal and result."))
		dap.create_break_timesheet(
			from_time=break_from,
			project=break_project,
			goal=break_goal.strip(),
			result=break_result.strip(),
			percent_billable=break_percent_billable,
			activity_type=break_activity_type or None,
		)
	dap.resume_timer(name)
	return get_timer_state()


def stop_timer(name, result, percent_billable=100, activity_type=None, manual_end_time=None):
	doc = _own_record(name)
	result = (result or "").strip()
	if not result:
		frappe.throw(_("Please describe what you accomplished."))
	if not activity_type:
		frappe.throw(_("Please pick an activity type."))
	if str(percent_billable) not in BILLABLE_OPTIONS:
		frappe.throw(_("Billable share must be 0, 25, 50, 75 or 100 %."))
	open_from = next((row.from_time for row in reversed(doc.item) if not row.to_time), None)
	if manual_end_time and open_from and get_datetime(manual_end_time) < get_datetime(open_from):
		frappe.throw(_("The end time cannot be before the start of the current segment."))
	outcome = dap.stop_timer(
		name,
		result,
		percent_billable=percent_billable,
		activity_type=activity_type,
		manual_end_time=manual_end_time or None,
	)
	return {"outcome": outcome, "state": get_timer_state()}


def continue_with_available_hours(name):
	_own_record(name)
	submit_at_available_hours(name)
	return get_timer_state()


def notify_account_manager(name):
	_own_record(name)
	notify_pm_of_time_limit(name)
	return get_timer_state()


def discard_draft(name):
	"""Delete one of my drafts that holds no time at all (it only blocks new timers)."""
	doc = _own_record(name)
	if doc.docstatus != 0 or doc.item:
		frappe.throw(_("Only empty drafts can be discarded here. Open the record in Desk instead."))
	frappe.delete_doc(DOCTYPE, name, ignore_permissions=True)
	return get_timer_state()
