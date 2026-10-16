# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Personal Cockpit API — the Issues, Tasks and Checklists assigned to the session user.

Same endpoints as the department cockpits, so the shared spa_shared views work
unchanged; the personal scope lives in department_cockpit (scope="personal").
"""

import frappe

from phamos.api import department_cockpit as dc
from phamos.api import personal_todos
from phamos.api import personal_todo_dashboard
from phamos.api import personal_todo_matrix
from phamos.api import personal_focus
from phamos.api import personal_challenges
from phamos.api import personal_day_plan
from phamos.api import personal_checkin
from phamos.api import personal_timer
from phamos.api import personal_timeline

CONFIG = dc.CockpitConfig(
	label="Personal Cockpit",
	department_field="",
	project_field="",
	roles=("Employee",),  # assignee shortlist only, not a permission gate
	settings_method_name="get_personal_settings",
	scope="personal",
)


def check_app_permission():
	"""Show the Personal Cockpit on the Apps screen for every System User."""
	return dc.check_app_permission(CONFIG)


@frappe.whitelist()
def get_personal_settings():
	"""Return the Personal Cockpit configuration for the frontend (nothing to configure yet)."""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks of a project (timesheet start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return my Issues: assigned | created (assigned only, intersected)."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
def get_issues(include_closed=0):
	"""Return the Issues assigned to me."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it is assigned to me or created by me."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
def get_form_options():
	"""Form options: all departments, open projects, Employee shortlist."""
	return dc.get_form_options(CONFIG)


@frappe.whitelist(methods=["POST"])
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create an Issue, assigned to me unless assignees are given."""
	return dc.create_issue(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


@frappe.whitelist(methods=["POST"])
def update_status(name, status):
	"""Update the status of one of my Issues."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def set_assignees(name, users=None):
	"""Replace the assignees of one of my Issues."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
def update_issue(
	name, subject=None, description=None, priority=None, issue_type=None, project=None, modified=None
):
	"""Autosave whitelisted fields of one of my Issues."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if issue_type is not None:
		fields["issue_type"] = issue_type
	if project is not None:
		fields["project"] = project
	if modified is not None:
		fields["modified"] = modified
	return dc.update_issue(CONFIG, name, **fields)


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return the Tasks assigned to me."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklists(include_completed=0):
	"""Return Checklists I own or that are linked to my Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklist_dashboard():
	"""Return dashboard metrics for my Checklists."""
	return dc.get_checklist_dashboard(CONFIG)


@frappe.whitelist(methods=["POST"])
def create_checklist(
	document,
	reference_record,
	name=None,
	items=None,
	checklist_owner=None,
	checklist_template=None,
):
	"""Create a Checklist on one of my Issues or Tasks."""
	return dc.create_checklist(
		CONFIG,
		document,
		reference_record,
		name=name,
		items=items,
		checklist_owner=checklist_owner,
		checklist_template=checklist_template,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def checklist_reference_query(doctype, txt, searchfield, start, page_len, filters):
	"""Search my Issues/Tasks as Checklist parents."""
	return dc.checklist_reference_query(CONFIG, doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
def get_task(name):
	"""Return Task detail if it is assigned to me or created by me."""
	return dc.get_task(CONFIG, name)


@frappe.whitelist(methods=["POST"])
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	return dc.update_task_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	return dc.update_task_dates(CONFIG, name, exp_start_date=exp_start_date, exp_end_date=exp_end_date)


@frappe.whitelist(methods=["POST"])
def update_task(
	name,
	subject=None,
	description=None,
	priority=None,
	status=None,
	exp_start_date=None,
	exp_end_date=None,
	progress=None,
	project=None,
	modified=None,
):
	"""Autosave whitelisted fields of one of my Tasks."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if status is not None:
		fields["status"] = status
	if exp_start_date is not None:
		fields["exp_start_date"] = exp_start_date
	if exp_end_date is not None:
		fields["exp_end_date"] = exp_end_date
	if progress is not None:
		fields["progress"] = progress
	if project is not None:
		fields["project"] = project
	if modified is not None:
		fields["modified"] = modified
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
def set_task_assignees(name, users=None):
	"""Replace the assignees of one of my Tasks."""
	return dc.set_task_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
):
	"""Create a Task assigned to me (department taken from the project)."""
	return dc.create_task(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		project=project,
		department=department,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
	)


@frappe.whitelist(methods=["POST"])
def create_task_from_issue(
	issue_name,
	exp_start_date,
	exp_end_date,
	assignees=None,
	subject=None,
	description=None,
	priority=None,
	project=None,
	depends_on=None,
):
	"""Convert one of my Issues into a Task."""
	return dc.create_task_from_issue(
		CONFIG,
		issue_name,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		assignees=assignees,
		subject=subject,
		description=description,
		priority=priority,
		project=project,
		depends_on=depends_on,
	)


@frappe.whitelist(methods=["POST"])
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)


# ToDos (phamos/phamos#1541) — logic in phamos.api.personal_todos.


@frappe.whitelist()
def get_my_todos(include_closed=0):
	"""Return my ToDos sorted by due date, then priority (High first)."""
	return personal_todos.get_my_todos(include_closed=include_closed)


@frappe.whitelist()
def get_todo(name):
	"""Return one of my ToDos."""
	return personal_todos.get_todo(name)


@frappe.whitelist()
def get_todo_reference_types():
	"""Reference types offered when creating a ToDo."""
	return personal_todos.get_reference_types()


@frappe.whitelist(methods=["POST"])
def create_todo(description, date=None, priority=None, reference_type=None, reference_name=None):
	"""Create a ToDo for me, optionally referencing a record."""
	return personal_todos.create_todo(
		description,
		date=date,
		priority=priority,
		reference_type=reference_type,
		reference_name=reference_name,
	)


@frappe.whitelist(methods=["POST"])
def update_todo(
	name, description=None, date=None, priority=None, modified=None, important=None, estimate_minutes=None
):
	"""Update description, due date, priority, importance or estimate of one of my ToDos."""
	return personal_todos.update_todo(
		name,
		description=description,
		date=date,
		priority=priority,
		modified=modified,
		important=important,
		estimate_minutes=estimate_minutes,
	)


@frappe.whitelist(methods=["POST"])
def close_todo(name):
	"""Mark one of my ToDos as done."""
	return personal_todos.set_status(name, "Closed")


@frappe.whitelist(methods=["POST"])
def reopen_todo(name):
	"""Reopen one of my closed ToDos."""
	return personal_todos.set_status(name, "Open")


# ToDo dashboard and decisions (phamos/phamos#1553).


@frappe.whitelist()
def get_todo_dashboard(period=30):
	"""Open vs closed ratio, backlog flow, lead time, age and stale ToDos for the session user."""
	return personal_todo_dashboard.get_todo_dashboard(period=period)


@frappe.whitelist(methods=["POST"])
def decide_todo(name, action, date=None, reason=None):
	"""Decide on one of my ToDos: today, later this week, a chosen date, or drop (with a reason)."""
	return personal_todos.decide_todo(name, action, date=date, reason=reason)


# Eisenhower matrix (phamos/phamos#1555) — logic in phamos.api.personal_todo_matrix.


@frappe.whitelist()
def get_todo_matrix(scope="week"):
	"""Return my open ToDos sorted into the four Eisenhower quadrants."""
	return personal_todo_matrix.get_matrix(scope=scope)


@frappe.whitelist(methods=["POST"])
def set_todo_quadrant(name, quadrant, date=None, payoff_note=None):
	"""Move one of my ToDos into a quadrant (sets the important flag and, if needed, the date)."""
	return personal_todo_matrix.set_quadrant(name, quadrant, date=date, payoff_note=payoff_note)


# Focus mode (phamos/phamos#1556) — logic in phamos.api.personal_focus.


@frappe.whitelist()
def get_active_focus():
	"""My running focus session, or None."""
	return personal_focus.get_active_focus()


@frappe.whitelist()
def get_focus_options():
	return personal_focus.get_focus_options()


@frappe.whitelist()
def get_focus_session(name):
	return personal_focus.get_focus_session(name)


@frappe.whitelist()
def get_focus_history(limit=10):
	return personal_focus.get_focus_history(limit=limit)


@frappe.whitelist(methods=["POST"])
def start_focus(todos, minutes=25):
	"""Lock in 1–5 of my open ToDos for `minutes` (0 = stopwatch)."""
	return personal_focus.start_focus(todos, minutes=minutes)


@frappe.whitelist(methods=["POST"])
def focus_switch(todo):
	return personal_focus.focus_switch(todo)


@frappe.whitelist(methods=["POST"])
def focus_mark_done(todo):
	return personal_focus.focus_mark_done(todo)


@frappe.whitelist(methods=["POST"])
def focus_park(todo, resume_note=None):
	return personal_focus.focus_park(todo, resume_note=resume_note)


@frappe.whitelist(methods=["POST"])
def end_focus(outcome="Broke out", reason=None, resume_note=None):
	"""End my focus session. Always allowed."""
	return personal_focus.end_focus(outcome=outcome, reason=reason, resume_note=resume_note)


# ToDo challenges (phamos/phamos#1557) — logic in phamos.api.personal_challenges.


@frappe.whitelist()
def get_challenges():
	"""My running challenges with today's progress, and the latest finished ones."""
	return personal_challenges.get_challenges()


@frappe.whitelist()
def suggest_challenge(kind="Closes per day"):
	"""A target from my own history (median closes per working day × 1.2)."""
	return personal_challenges.suggest_challenge(kind=kind)


@frappe.whitelist(methods=["POST"])
def create_challenge(
	kind, target_per_day=None, working_days=10, start_date=None, title=None, target_planned=None, target_spontaneous=None
):
	return personal_challenges.create_challenge(
		kind,
		target_per_day,
		working_days=working_days,
		start_date=start_date,
		title=title,
		target_planned=target_planned,
		target_spontaneous=target_spontaneous,
	)


@frappe.whitelist(methods=["POST"])
def end_challenge(name):
	return personal_challenges.end_challenge(name)


# My Day (phamos/phamos#1559) — logic in phamos.api.personal_day_plan.


@frappe.whitelist()
def get_day_plan(date=None):
	"""My plan for a day (today by default) with candidates, capacity and calibration."""
	return personal_day_plan.get_day_plan(date=date)


@frappe.whitelist()
def get_day_state():
	return personal_day_plan.get_day_state()


@frappe.whitelist(methods=["POST"])
def add_to_day(todo, date=None):
	return personal_day_plan.add_to_day(todo, date=date)


@frappe.whitelist(methods=["POST"])
def remove_from_day(todo, date=None):
	return personal_day_plan.remove_from_day(todo, date=date)


@frappe.whitelist(methods=["POST"])
def move_in_day(todo, direction, date=None):
	return personal_day_plan.move_in_day(todo, direction, date=date)


@frappe.whitelist(methods=["POST"])
def start_day(date=None):
	"""Fix today's plan; ToDos added later count as spontaneous."""
	return personal_day_plan.start_day(date=date)


@frappe.whitelist(methods=["POST"])
def shutdown_day(decisions=None, reflection=None, date=None):
	"""Close the day with a decision for every open ToDo on the plan."""
	return personal_day_plan.shutdown_day(decisions=decisions, reflection=reflection, date=date)


# Check-in and check-out (phamos/phamos#1571) — logic in phamos.api.personal_checkin.


@frappe.whitelist()
def get_checkin_state():
	"""My last check-in, the next action (IN/OUT) and today's logs with worked minutes."""
	return personal_checkin.get_checkin_state()


@frappe.whitelist(methods=["POST"])
def add_checkin(log_type, latitude=None, longitude=None):
	"""Check in or out now (server time). Refused when it is not the expected next action."""
	return personal_checkin.add_checkin(log_type, latitude=latitude, longitude=longitude)


@frappe.whitelist(methods=["POST"])
def revoke_checkin(name):
	"""Undo a check-in I made moments ago."""
	return personal_checkin.revoke_checkin(name)


# Timesheet timer (phamos/phamos#1572) — logic in phamos.api.personal_timer, on top of the
# Developer Action Panel functions; every call checks that the record is mine.


@frappe.whitelist()
def get_timer_state():
	"""My running or paused timer, or what blocks starting one."""
	return personal_timer.get_timer_state()


@frappe.whitelist()
def get_timer_options():
	"""My projects, recent projects and activity types for the start and stop dialogs."""
	return personal_timer.get_timer_options()


@frappe.whitelist()
def search_timer_projects(txt=""):
	return personal_timer.search_timer_projects(txt)


@frappe.whitelist()
def get_timer_project_info(project):
	"""Task rule, open tasks and default billable share of a project."""
	return personal_timer.get_timer_project_info(project)


@frappe.whitelist(methods=["POST"])
def start_timer(project, expected_seconds, goal, task=None, manual_start_time=None):
	return personal_timer.start_timer(project, expected_seconds, goal, task=task, manual_start_time=manual_start_time)


@frappe.whitelist(methods=["POST"])
def pause_timer(name):
	return personal_timer.pause_timer(name)


@frappe.whitelist(methods=["POST"])
def resume_timer(name, break_project=None, break_goal=None, break_result=None, break_activity_type=None, break_percent_billable=0):
	return personal_timer.resume_timer(
		name,
		break_project=break_project,
		break_goal=break_goal,
		break_result=break_result,
		break_activity_type=break_activity_type,
		break_percent_billable=break_percent_billable,
	)


@frappe.whitelist(methods=["POST"])
def stop_timer(name, result, percent_billable=100, activity_type=None, manual_end_time=None):
	return personal_timer.stop_timer(
		name, result, percent_billable=percent_billable, activity_type=activity_type, manual_end_time=manual_end_time
	)


@frappe.whitelist(methods=["POST"])
def continue_timer_with_available_hours(name):
	return personal_timer.continue_with_available_hours(name)


@frappe.whitelist(methods=["POST"])
def notify_timer_account_manager(name):
	return personal_timer.notify_account_manager(name)


@frappe.whitelist(methods=["POST"])
def discard_timer_draft(name):
	return personal_timer.discard_draft(name)


# My Day timeline (phamos/phamos#1573) — logic in phamos.api.personal_timeline.


@frappe.whitelist()
def get_timeline(from_date, to_date):
	"""My check-ins, time logs, closed ToDos and day plans for up to 31 days."""
	return personal_timeline.get_timeline(from_date, to_date)
