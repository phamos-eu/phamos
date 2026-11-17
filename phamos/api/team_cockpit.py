# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit API: Issues, Tasks and Checklists of the session user's active Team (#1955).

The team is not an argument: phamos.cockpits.teams resolves it per request from the user's
membership, so the shared cockpit views work unchanged. Every whitelisted function first checks
that the user has a team at all.
"""

import functools

import frappe
from frappe import _

from phamos.api import department_cockpit as dc
from phamos.cockpits import teams

CONFIG = dc.CockpitConfig(
	label="Team",
	department_field="",
	project_field="",
	roles=(),
	settings_method_name="get_team_settings",
	scope="team",
)


def check_app_permission():
	"""True for users who may open at least one team (Apps screen, page, API)."""
	return dc.check_app_permission(CONFIG)


def _require_access(fn):
	"""Refuse a whitelisted call unless check_app_permission() passes.

	functools.wraps keeps the signature, which frappe uses to pick the request arguments.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if not check_app_permission():
			frappe.throw(_("You do not have permission to access the Team Cockpit"), frappe.PermissionError)
		return fn(*args, **kwargs)

	# Marker for the tests; functools.wraps carries it up through frappe.whitelist's own wrapper.
	wrapper.requires_team = True
	return wrapper


def _team_rows(names):
	return [{"name": name} for name in names]


@frappe.whitelist()
@_require_access
def get_teams():
	"""The teams the session user may open, and the one the cockpit shows now.

	Returns:
		dict: teams ([{name}], sorted by name) and active (a team name).
	"""
	return {"teams": _team_rows(teams.available_teams()), "active": teams.active_team()}


@frappe.whitelist(methods=["POST"])
@_require_access
def set_active_team(team):
	"""Show `team` in the session user's Team Cockpit from now on. Only a team they may open."""
	teams.set_active_team(team)
	return get_teams()


@frappe.whitelist()
@_require_access
def get_team_settings():
	"""Return the Team Cockpit configuration for the frontend.

	Requires read permission on Issue (checked in department_cockpit.get_settings).

	Returns:
		dict: team (the active team's name) and teams (every team the user may open).
	"""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
@_require_access
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the team timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
@_require_access
def get_inbox(view="assigned", include_closed=0):
	"""Return team-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issues(include_closed=0):
	"""Return all team Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issue(name):
	"""Return Issue detail if it belongs to team scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_form_options():
	"""Form options scoped to team."""
	return dc.get_form_options(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create a team-scoped Issue."""
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
@_require_access
def update_status(name, status):
	"""Update Issue status within team scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_assignees(name, users=None):
	"""Replace Issue assignees within team scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist()
@_require_access
def get_issue_chat(name):
	"""Return the Raven chat state of an Issue in team scope."""
	return dc.get_issue_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_issue_chat(name):
	"""Start or join the Raven chat of an Issue in team scope."""
	return dc.ensure_issue_chat(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_issue_chat_states(names):
	"""Return the chat state per Issue for list views."""
	return dc.get_issue_chat_states(names)


@frappe.whitelist()
@_require_access
def get_task_chat(name):
	"""Return the Raven chat state of a Task in team scope."""
	return dc.get_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_task_chat(name):
	"""Start or join the Raven chat of a Task in team scope."""
	return dc.ensure_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_issue(
	name, subject=None, description=None, priority=None, issue_type=None, project=None, modified=None
):
	"""Update whitelisted Issue fields within team scope."""
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
@_require_access
def get_tasks(include_completed=0):
	"""Return Tasks for the team."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklists(include_completed=0):
	"""Return Checklists linked to team Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklist_dashboard():
	"""Return team Checklist dashboard metrics and chart data."""
	return dc.get_checklist_dashboard(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_checklist(
	document,
	reference_record,
	name=None,
	items=None,
	checklist_owner=None,
	checklist_template=None,
):
	"""Create a Checklist linked to a team Issue or Task."""
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
@_require_access
def checklist_reference_query(doctype, txt, searchfield, start, page_len, filters):
	"""Search team-scoped Issue/Task parents for Checklist creation."""
	return dc.checklist_reference_query(CONFIG, doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
@_require_access
def get_task(name):
	"""Return Task detail for the team SPA."""
	return dc.get_task(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	return dc.update_task_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	return dc.update_task_dates(CONFIG, name, exp_start_date=exp_start_date, exp_end_date=exp_end_date)


@frappe.whitelist(methods=["POST"])
@_require_access
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
	custom_task_owner=None,
	modified=None,
):
	"""Update whitelisted Task fields within team scope."""
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
	if custom_task_owner is not None:
		fields["custom_task_owner"] = custom_task_owner
	if modified is not None:
		fields["modified"] = modified
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_task_assignees(name, users=None):
	"""Replace Task assignees within team scope."""
	return dc.set_task_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
	expected_time=None,
	custom_task_owner=None,
	task_type=None,
):
	"""Create a Task in the team."""
	return dc.create_task(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		project=project,
		department=department,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		expected_time=expected_time,
		custom_task_owner=custom_task_owner,
		task_type=task_type,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
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
	"""Convert an Issue into a Task (Team Cockpit hand-off)."""
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
@_require_access
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)
