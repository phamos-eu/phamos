# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""HR SPA API — department-scoped Issues and Tasks."""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.load import get_assignments
from frappe.utils import get_fullname

from phamos.api.i_own_my_work import (
	ALLOWED_STATUSES,
	LIST_FIELDS,
	_parse_assignees,
	_parse_list,
	_serialize_issue_row,
	_status_filters,
)
from phamos.api.i_own_my_work import get_issue as _get_issue
from phamos.api.i_own_my_work import set_assignees as _set_assignees
from phamos.api.i_own_my_work import update_status as _update_status

TASK_LIST_FIELDS = [
	"name",
	"subject",
	"description",
	"status",
	"priority",
	"project",
	"department",
	"exp_start_date",
	"exp_end_date",
	"progress",
	"color",
	"depends_on_tasks",
	"modified",
	"_assign",
]

TASK_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled", "Template")
TASK_KANBAN_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed")
TASK_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")


def check_app_permission():
	"""Show HR SPA on the Apps screen for eligible users."""
	if frappe.session.user in (None, "Guest"):
		return False
	if frappe.session.user == "Administrator":
		return True

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False

	roles = set(frappe.get_roles())
	if roles & {"System Manager", "HR Manager", "HR User"}:
		return True

	return frappe.has_permission("Issue", ptype="read") or frappe.has_permission("Task", ptype="read")


def _user_label(user):
	if not user:
		return ""
	return get_fullname(user) or user


def _get_hr_settings_doc():
	return frappe.get_cached_doc("phamos Settings")


def _get_hr_department():
	return frappe.db.get_single_value("phamos Settings", "hr_department")


def _get_hr_timesheet_project():
	return frappe.db.get_single_value("phamos Settings", "hr_timesheet_project")


def _get_hr_project_names(department=None):
	"""Projects linked to the HR department."""
	department = department or _get_hr_department()
	if not department:
		return []
	return frappe.get_all(
		"Project",
		filters={"department": department},
		pluck="name",
		limit_page_length=500,
	)


def _hr_issue_or_filters(department=None):
	"""Match issues scoped to HR via project department or Issue.custom_department."""
	department = department or _get_hr_department()
	if not department:
		return []

	or_filters = []
	project_names = _get_hr_project_names(department)
	if project_names:
		or_filters.append(["project", "in", project_names])
	if frappe.get_meta("Issue").has_field("custom_department"):
		or_filters.append(["custom_department", "=", department])
	return or_filters


def _issue_in_hr_scope(doc):
	"""True when issue belongs to the configured HR department."""
	department = _get_hr_department()
	if not department:
		return False

	if getattr(doc, "custom_department", None) == department:
		return True

	if doc.project:
		project_department = frappe.db.get_value("Project", doc.project, "department")
		if project_department == department:
			return True

	return False


def _ensure_issue_in_hr_scope(doc):
	if not _issue_in_hr_scope(doc):
		frappe.throw(_("This issue is not in the HR department scope."))


def _require_hr_department():
	department = _get_hr_department()
	if not department:
		frappe.throw(
			_("HR Department is not configured in phamos Settings."),
			title=_("Configuration required"),
		)
	return department


def _validate_hr_project(project):
	if not project:
		frappe.throw(_("Project is required for HR issues."))
	department = _require_hr_department()
	project_department = frappe.db.get_value("Project", project, "department")
	if project_department != department:
		frappe.throw(
			_("Project {0} is not linked to HR department {1}.").format(project, department)
		)


@frappe.whitelist()
def get_hr_settings():
	"""Return HR SPA configuration for the frontend."""
	frappe.has_permission("Issue", "read", throw=True)

	from phamos.api.issue_raven import get_chat_feature_flags

	department = _get_hr_department()
	timesheet_project = _get_hr_timesheet_project()
	project_names = _get_hr_project_names(department)

	project_label = None
	if timesheet_project:
		project_label = frappe.db.get_value("Project", timesheet_project, "project_name") or timesheet_project

	return {
		"hr_department": department,
		"hr_timesheet_project": timesheet_project,
		"hr_timesheet_project_name": project_label,
		"hr_project_count": len(project_names),
		"chat": get_chat_feature_flags(),
	}


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the HR timesheet project (start-modal dropdown)."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_hr_department()
	project = project or _get_hr_timesheet_project()
	if not project:
		return []

	_validate_hr_project(project)

	rows = frappe.get_list(
		"Task",
		filters={
			"department": department,
			"project": project,
			"status": ("not in", ["Cancelled", "Template", "Completed"]),
		},
		fields=["name", "subject"],
		order_by="modified desc",
		limit_page_length=200,
	)
	return rows


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return HR-scoped Issues for the current user: assigned | created."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_hr_department()

	view = (view or "assigned").lower()
	include_closed = frappe.utils.cint(include_closed)
	user = frappe.session.user
	filters = _status_filters(include_closed)
	or_filters = _hr_issue_or_filters()
	if not or_filters:
		return []

	if view == "created":
		filters.append(["owner", "=", user])
		rows = frappe.get_list(
			"Issue",
			filters=filters,
			or_filters=or_filters,
			fields=LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=200,
		)
	else:
		todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Issue",
				"allocated_to": user,
				"status": ("not in", ("Cancelled", "Closed")),
			},
			fields=["reference_name"],
			limit_page_length=500,
		)
		names = list({t.reference_name for t in todos if t.reference_name})
		if not names:
			return []
		filters.append(["name", "in", names])
		rows = frappe.get_list(
			"Issue",
			filters=filters,
			or_filters=or_filters,
			fields=LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=200,
		)

	return [_serialize_issue_row(r) for r in rows]


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to HR scope."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_hr_department()

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	_ensure_issue_in_hr_scope(doc)

	return _get_issue(name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to HR department."""
	frappe.has_permission("Issue", "read", throw=True)
	department = _require_hr_department()

	from phamos.api.i_own_my_work import get_form_options as _base_options

	options = _base_options()
	project_names = set(_get_hr_project_names(department))
	timesheet_project = _get_hr_timesheet_project()
	if timesheet_project:
		project_names.add(timesheet_project)
	options["departments"] = [department]
	if project_names:
		options["projects"] = [p for p in options.get("projects", []) if p["name"] in project_names]
	options["hr_department"] = department
	options["hr_timesheet_project"] = _get_hr_timesheet_project()
	options["chat"] = get_chat_settings()
	return options


@frappe.whitelist()
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
	frappe.has_permission("Issue", "create", throw=True)
	hr_department = _require_hr_department()

	if not project:
		project = _get_hr_timesheet_project()
	if not department:
		department = hr_department

	if department != hr_department and project:
		_validate_hr_project(project)

	from phamos.api.i_own_my_work import create_issue as _create

	return _create(
		subject=subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


@frappe.whitelist()
def update_status(name, status):
	"""Update Issue status within HR scope."""
	get_issue(name)
	return _update_status(name, status)


@frappe.whitelist()
def set_assignees(name, users=None):
	"""Replace Issue assignees within HR scope."""
	get_issue(name)
	return _set_assignees(name, users)


def _serialize_task_row(row):
	assignees = _parse_assignees(row.get("_assign"))
	return {
		"name": row.get("name"),
		"subject": row.get("subject"),
		"description": row.get("description") or "",
		"status": row.get("status"),
		"priority": row.get("priority"),
		"project": row.get("project"),
		"department": row.get("department"),
		"exp_start_date": row.get("exp_start_date"),
		"exp_end_date": row.get("exp_end_date"),
		"progress": row.get("progress") or 0,
		"color": row.get("color"),
		"depends_on_tasks": row.get("depends_on_tasks") or "",
		"modified": row.get("modified"),
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
	}


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return Tasks for the HR department."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_hr_department()
	include_completed = frappe.utils.cint(include_completed)

	filters = [["department", "=", department]]
	if not include_completed:
		filters.append(["status", "not in", ["Cancelled", "Template", "Completed"]])

	rows = frappe.get_list(
		"Task",
		filters=filters,
		fields=TASK_LIST_FIELDS,
		order_by="exp_start_date asc, modified desc",
		limit_page_length=500,
	)
	return [_serialize_task_row(r) for r in rows]


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the HR SPA."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_hr_department()

	doc = frappe.get_doc("Task", name)
	doc.check_permission("read")
	if doc.department != department:
		frappe.throw(_("This task is not in the HR department."))

	assignees = [a.get("owner") for a in get_assignments("Task", doc.name)]
	return {
		"name": doc.name,
		"subject": doc.subject,
		"description": doc.description or "",
		"status": doc.status,
		"priority": doc.priority,
		"project": doc.project,
		"department": doc.department,
		"exp_start_date": doc.exp_start_date,
		"exp_end_date": doc.exp_end_date,
		"progress": doc.progress or 0,
		"color": doc.color,
		"depends_on_tasks": doc.depends_on_tasks or "",
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"modified": doc.modified,
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
		"desk_url": f"/app/task/{doc.name}",
	}


@frappe.whitelist()
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	frappe.has_permission("Task", "write", throw=True)
	status = (status or "").strip()
	if status not in TASK_KANBAN_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))

	get_task(name)
	doc = frappe.get_doc("Task", name)
	doc.status = status
	doc.save()
	return get_task(name)


@frappe.whitelist()
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(name)

	doc = frappe.get_doc("Task", name)
	if exp_start_date:
		doc.exp_start_date = exp_start_date
	if exp_end_date:
		doc.exp_end_date = exp_end_date
	doc.save()
	return get_task(name)


@frappe.whitelist()
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
	frappe.has_permission("Task", "create", throw=True)
	hr_department = _require_hr_department()

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	if not department:
		department = hr_department
	if department != hr_department:
		frappe.throw(_("Task department must match HR department in phamos Settings."))

	if not project:
		project = _get_hr_timesheet_project()
	if project:
		_validate_hr_project(project)

	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": "Open",
			"department": department,
			"project": project,
		}
	)
	if description:
		doc.description = description
	if priority:
		doc.priority = priority
	if exp_start_date:
		doc.exp_start_date = exp_start_date
	if exp_end_date:
		doc.exp_end_date = exp_end_date
	doc.insert()
	return get_task(doc.name)


@frappe.whitelist()
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(name)
	get_task(depends_on)

	if name == depends_on:
		frappe.throw(_("A task cannot depend on itself."))

	doc = frappe.get_doc("Task", name)
	existing = {row.task for row in doc.depends_on if row.task}
	if depends_on in existing:
		return get_task(name)

	doc.append("depends_on", {"task": depends_on})
	doc.save()
	return get_task(name)


@frappe.whitelist()
def get_chat_settings():
	"""SPA soft-dependency flags for Raven chat."""
	from phamos.api.issue_raven import get_chat_feature_flags

	return get_chat_feature_flags()


# Re-export Raven chat APIs for a stable SPA method prefix
from phamos.api.issue_raven import (  # noqa: E402, F401
	ensure_document_channel,
	get_chat_messages,
	get_document_chat,
	get_raven_users_for_invite,
	get_thread,
	invite_to_document_channel,
	open_or_create_thread,
	send_chat_message,
)
