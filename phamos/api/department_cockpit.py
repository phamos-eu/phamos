# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Shared department cockpit API — Issues, Tasks, inbox, and timesheet settings."""

from dataclasses import dataclass
from typing import Callable, Optional

import frappe
from frappe import _
from frappe.desk.form.load import get_assignments
from frappe.utils import get_fullname

from phamos.api.i_own_my_work import (
	LIST_FIELDS,
	_parse_assignees,
	_serialize_issue_row,
	_status_filters,
)
from phamos.api.i_own_my_work import create_issue as _create_issue
from phamos.api.i_own_my_work import get_form_options as _base_form_options
from phamos.api.i_own_my_work import get_issue as _get_issue_detail
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

TASK_KANBAN_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed")


@dataclass(frozen=True)
class CockpitConfig:
	"""Per-department cockpit configuration bound to phamos Settings fields."""

	label: str
	department_field: str
	project_field: str
	roles: tuple
	settings_method_name: str = ""

	@property
	def project_name_key(self) -> str:
		return f"{self.project_field}_name"

	@property
	def project_count_key(self) -> str:
		prefix = self.department_field.replace("_department", "")
		return f"{prefix}_project_count"


def _user_label(user):
	if not user:
		return ""
	return get_fullname(user) or user


def _get_department(config: CockpitConfig):
	return frappe.db.get_single_value("phamos Settings", config.department_field)


def _get_project(config: CockpitConfig):
	return frappe.db.get_single_value("phamos Settings", config.project_field)


def _get_project_names(config: CockpitConfig, department=None):
	department = department or _get_department(config)
	if not department:
		return []
	return frappe.get_all(
		"Project",
		filters={"department": department},
		pluck="name",
		limit_page_length=500,
	)


def _issue_or_filters(config: CockpitConfig, department=None):
	department = department or _get_department(config)
	if not department:
		return []

	or_filters = []
	project_names = _get_project_names(config, department)
	if project_names:
		or_filters.append(["project", "in", project_names])
	if frappe.get_meta("Issue").has_field("custom_department"):
		or_filters.append(["custom_department", "=", department])
	return or_filters


def _issue_in_scope(config: CockpitConfig, doc):
	department = _get_department(config)
	if not department:
		return False

	if getattr(doc, "custom_department", None) == department:
		return True

	if doc.project:
		project_department = frappe.db.get_value("Project", doc.project, "department")
		if project_department == department:
			return True

	return False


def _ensure_issue_in_scope(config: CockpitConfig, doc):
	if not _issue_in_scope(config, doc):
		frappe.throw(
			_("This issue is not in the {0} department scope.").format(config.label)
		)


def _require_department(config: CockpitConfig):
	department = _get_department(config)
	if not department:
		frappe.throw(
			_("{0} Department is not configured in phamos Settings.").format(config.label),
			title=_("Configuration required"),
		)
	return department


def validate_project(config: CockpitConfig, project):
	if not project:
		frappe.throw(_("Project is required for {0} issues.").format(config.label))
	department = _require_department(config)
	project_department = frappe.db.get_value("Project", project, "department")
	if project_department != department:
		frappe.throw(
			_("Project {0} is not linked to {1} department {2}.").format(
				project, config.label, department
			)
		)


def check_app_permission(config: CockpitConfig, extra_doctypes=()):
	if frappe.session.user in (None, "Guest"):
		return False
	if frappe.session.user == "Administrator":
		return True

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False

	roles = set(frappe.get_roles())
	if roles & set(config.roles):
		return True

	if frappe.has_permission("Issue", ptype="read") or frappe.has_permission("Task", ptype="read"):
		return True

	for doctype in extra_doctypes:
		if frappe.has_permission(doctype, ptype="read"):
			return True

	return False


def get_settings(config: CockpitConfig, read_permission: Optional[Callable[[], None]] = None):
	"""Return SPA configuration for the frontend."""
	if read_permission:
		read_permission()
	else:
		frappe.has_permission("Issue", "read", throw=True)

	from phamos.api.issue_raven import get_chat_feature_flags

	department = _get_department(config)
	project = _get_project(config)
	project_names = _get_project_names(config, department)

	project_label = None
	if project:
		project_label = frappe.db.get_value("Project", project, "project_name") or project

	return {
		config.department_field: department,
		config.project_field: project,
		config.project_name_key: project_label,
		config.project_count_key: len(project_names),
		"chat": get_chat_feature_flags(),
	}


def get_timesheet_project_tasks(config: CockpitConfig, project=None):
	"""Return open Tasks for the configured timesheet/standard project."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_department(config)
	project = project or _get_project(config)
	if not project:
		return []

	validate_project(config, project)

	return frappe.get_list(
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


def get_inbox(config: CockpitConfig, view="assigned", include_closed=0):
	"""Return department-scoped Issues for the current user: assigned | created."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_department(config)

	view = (view or "assigned").lower()
	include_closed = frappe.utils.cint(include_closed)
	user = frappe.session.user
	filters = _status_filters(include_closed)
	or_filters = _issue_or_filters(config)
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


def get_issue(config: CockpitConfig, name):
	"""Return Issue detail if it belongs to department scope."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_department(config)

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	_ensure_issue_in_scope(config, doc)

	return _get_issue_detail(name)


def get_form_options(config: CockpitConfig):
	"""Form options scoped to the configured department."""
	frappe.has_permission("Issue", "read", throw=True)
	department = _require_department(config)

	options = _base_form_options()
	project_names = set(_get_project_names(config, department))
	standard_project = _get_project(config)
	if standard_project:
		project_names.add(standard_project)
	options["departments"] = [department]
	if project_names:
		options["projects"] = [p for p in options.get("projects", []) if p["name"] in project_names]
	options[config.department_field] = department
	options[config.project_field] = _get_project(config)
	options["chat"] = get_chat_settings()
	return options


def create_issue(
	config: CockpitConfig,
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create a department-scoped Issue."""
	frappe.has_permission("Issue", "create", throw=True)
	configured_department = _require_department(config)

	if not project:
		project = _get_project(config)
	if not department:
		department = configured_department

	if project:
		validate_project(config, project)

	return _create_issue(
		subject=subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


def update_status(config: CockpitConfig, name, status):
	"""Update Issue status within department scope."""
	get_issue(config, name)
	return _update_status(name, status)


def set_assignees(config: CockpitConfig, name, users=None):
	"""Replace Issue assignees within department scope."""
	get_issue(config, name)
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


def get_tasks(config: CockpitConfig, include_completed=0):
	"""Return Tasks for the configured department."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_department(config)
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


def get_task(config: CockpitConfig, name):
	"""Return Task detail for the department cockpit."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_department(config)

	doc = frappe.get_doc("Task", name)
	doc.check_permission("read")
	if doc.department != department:
		frappe.throw(_("This task is not in the {0} department.").format(config.label))

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


def update_task_status(config: CockpitConfig, name, status):
	"""Update Task status (Kanban drag)."""
	frappe.has_permission("Task", "write", throw=True)
	status = (status or "").strip()
	if status not in TASK_KANBAN_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))

	get_task(config, name)
	doc = frappe.get_doc("Task", name)
	doc.status = status
	doc.save()
	return get_task(config, name)


def update_task_dates(config: CockpitConfig, name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(config, name)

	doc = frappe.get_doc("Task", name)
	if exp_start_date:
		doc.exp_start_date = exp_start_date
	if exp_end_date:
		doc.exp_end_date = exp_end_date
	doc.save()
	return get_task(config, name)


def create_task(
	config: CockpitConfig,
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
):
	"""Create a Task in the configured department."""
	frappe.has_permission("Task", "create", throw=True)
	configured_department = _require_department(config)

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	if not department:
		department = configured_department
	if department != configured_department:
		frappe.throw(
			_("Task department must match {0} department in phamos Settings.").format(config.label)
		)

	if not project:
		project = _get_project(config)
	if project:
		validate_project(config, project)

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
	return get_task(config, doc.name)


def add_task_dependency(config: CockpitConfig, name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(config, name)
	get_task(config, depends_on)

	if name == depends_on:
		frappe.throw(_("A task cannot depend on itself."))

	doc = frappe.get_doc("Task", name)
	existing = {row.task for row in doc.depends_on if row.task}
	if depends_on in existing:
		return get_task(config, name)

	doc.append("depends_on", {"task": depends_on})
	doc.save()
	return get_task(config, name)


def get_chat_settings():
	"""SPA soft-dependency flags for Raven chat."""
	from phamos.api.issue_raven import get_chat_feature_flags

	return get_chat_feature_flags()
