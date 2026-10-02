# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Software Development cockpit API — department-scoped Issues, Tasks and Checklists."""

import frappe

from phamos.api import department_cockpit as dc

CONFIG = dc.CockpitConfig(
	label="Software Development",
	department_field="software_development_department",
	project_field="software_development_timesheet_project",
	roles=("System Manager", "Projects Manager", "Projects User"),
	settings_method_name="get_software_development_settings",
)


def check_app_permission():
	"""Show the Software Development cockpit on the Apps screen for eligible users."""
	return dc.check_app_permission(CONFIG)


@frappe.whitelist()
def get_software_development_settings():
	"""Return the Software Development cockpit configuration for the frontend.

	Requires read permission on Issue (checked in department_cockpit.get_settings).

	Returns:
		dict: software_development_department, software_development_timesheet_project,
		software_development_timesheet_project_name (the project's title) and
		software_development_project_count (projects linked to the department).
	"""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the Software Development timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return Software Development-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
def get_issues(include_closed=0):
	"""Return all Software Development department Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to Software Development scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to Software Development department."""
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
	"""Create a Software Development-scoped Issue."""
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
	"""Update Issue status within Software Development scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def set_assignees(name, users=None):
	"""Replace Issue assignees within Software Development scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
def update_issue(
	name, subject=None, description=None, priority=None, issue_type=None, project=None, modified=None
):
	"""Update whitelisted Issue fields within Software Development scope."""
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
	"""Return Tasks for the Software Development department."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklists(include_completed=0):
	"""Return Checklists linked to Software Development Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklist_dashboard():
	"""Return Software Development Checklist dashboard metrics and chart data."""
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
	"""Create a Checklist linked to a Software Development Issue or Task."""
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
	"""Search Software Development-scoped Issue/Task parents for Checklist creation."""
	return dc.checklist_reference_query(CONFIG, doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the Software Development SPA."""
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
	"""Update whitelisted Task fields within Software Development scope."""
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
	"""Replace Task assignees within Software Development scope."""
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
	"""Create a Task in the Software Development department."""
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
	"""Convert an Issue into a Task (Software Development cockpit hand-off)."""
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
