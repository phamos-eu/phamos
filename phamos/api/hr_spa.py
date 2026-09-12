# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""HR SPA API — department-scoped Issues and Tasks."""

import frappe

from phamos.api import department_cockpit as dc

CONFIG = dc.CockpitConfig(
	label="HR",
	department_field="hr_department",
	project_field="hr_timesheet_project",
	roles=("System Manager", "HR Manager", "HR User"),
	settings_method_name="get_hr_settings",
)


def check_app_permission():
	"""Show HR SPA on the Apps screen for eligible users."""
	return dc.check_app_permission(CONFIG)


@frappe.whitelist()
def get_hr_settings():
	"""Return HR SPA configuration for the frontend."""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the HR timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return HR-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
def get_issues(include_closed=0):
	"""Return all HR department Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to HR scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to HR department."""
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
	"""Create an HR-scoped Issue."""
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
	"""Update Issue status within HR scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def set_assignees(name, users=None):
	"""Replace Issue assignees within HR scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
def update_issue(name, subject=None, description=None, priority=None, issue_type=None, project=None):
	"""Update whitelisted Issue fields within HR scope."""
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
	return dc.update_issue(CONFIG, name, **fields)


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return Tasks for the HR department."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklists(include_completed=0):
	"""Return Checklists linked to HR Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the HR SPA."""
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
):
	"""Update whitelisted Task fields within HR scope."""
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
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
def set_task_assignees(name, users=None):
	"""Replace Task assignees within HR scope."""
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
	"""Create a Task in the HR department."""
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
):
	"""Convert an Issue into a Task (HR cockpit hand-off)."""
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
	)


@frappe.whitelist(methods=["POST"])
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)
