# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Shared department cockpit API — Issues, Tasks, inbox, and timesheet settings."""

from dataclasses import dataclass
from typing import Callable, Optional

import frappe
from frappe import _
from frappe.desk.form.load import get_assignments
from frappe.utils import get_fullname

from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment

from phamos.api.i_own_my_work import (
	LIST_FIELDS,
	_parse_assignees,
	_parse_list,
	_serialize_issue_row,
	_status_filters,
	enrich_issue_rows_for_search,
)
from phamos.api.i_own_my_work import create_issue as _create_issue
from phamos.api.i_own_my_work import get_form_options as _base_form_options
from phamos.api.i_own_my_work import set_assignees as _set_assignees
from phamos.api.i_own_my_work import update_status as _update_status

ISSUE_EDITABLE_FIELDS = ("subject", "description", "priority", "issue_type", "project")
TASK_EDITABLE_FIELDS = (
	"subject",
	"description",
	"priority",
	"status",
	"exp_start_date",
	"exp_end_date",
	"progress",
	"project",
)

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

	return enrich_issue_rows_for_search(rows)


def get_issues(config: CockpitConfig, include_closed=0):
	"""Return all department-scoped Issues (not limited to assigned/created)."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_department(config)

	include_closed = frappe.utils.cint(include_closed)
	filters = _status_filters(include_closed)
	or_filters = _issue_or_filters(config)
	if not or_filters:
		return []

	rows = frappe.get_list(
		"Issue",
		filters=filters,
		or_filters=or_filters,
		fields=LIST_FIELDS,
		order_by="modified desc",
		limit_page_length=200,
	)
	return enrich_issue_rows_for_search(rows)


def _user_images(users):
	"""Return user_image for each user name, preserving order."""
	if not users:
		return []
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", list(users))},
		fields=["name", "user_image"],
	)
	by_name = {r.name: r.user_image for r in rows}
	return [by_name.get(u) for u in users]


def _serialize_issue_detail(doc):
	"""Build SPA issue detail payload from an already-loaded Issue doc."""
	assignees = [a.get("owner") for a in get_assignments("Issue", doc.name)]
	return {
		"name": doc.name,
		"subject": doc.subject,
		"description": doc.description or "",
		"status": doc.status,
		"priority": doc.priority,
		"issue_type": doc.issue_type,
		"project": doc.project,
		"department": getattr(doc, "custom_department", None),
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"raised_by": doc.raised_by,
		"modified": doc.modified,
		"creation": doc.creation,
		"opening_date": getattr(doc, "opening_date", None),
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
		"assignee_images": _user_images(assignees),
		"desk_url": f"/app/issue/{doc.name}",
	}


def get_issue(config: CockpitConfig, name):
	"""Return Issue detail if it belongs to department scope."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_department(config)

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	_ensure_issue_in_scope(config, doc)

	return _serialize_issue_detail(doc)


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
	# Cockpits use a role shortlist + search_link; do not ship the full user dump.
	options.pop("users", None)
	options.pop("chat", None)
	options["shortlist_users"] = _role_shortlist_users(config)
	return options


def _role_shortlist_users(config: CockpitConfig, limit=50):
	"""Enabled System Users who hold any of the cockpit roles."""
	role_names = [r for r in (config.roles or ()) if r]
	if not role_names:
		return []

	user_names = set()
	for role in role_names:
		try:
			from frappe.utils.user import get_users_with_role

			user_names.update(get_users_with_role(role) or [])
		except Exception:
			rows = frappe.get_all(
				"Has Role",
				filters={"role": role, "parenttype": "User"},
				pluck="parent",
			)
			user_names.update(rows or [])

	user_names.discard("Guest")
	if not user_names:
		return []

	users = frappe.get_all(
		"User",
		filters={
			"name": ("in", list(user_names)),
			"enabled": 1,
			"user_type": "System User",
		},
		fields=["name", "full_name", "user_image"],
		order_by="full_name asc",
		limit_page_length=limit,
	)
	return [
		{"name": u.name, "full_name": u.full_name or u.name, "user_image": u.user_image}
		for u in users
	]


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


def update_issue(config: CockpitConfig, name, **fields):
	"""Update whitelisted Issue fields within department scope."""
	frappe.has_permission("Issue", "write", throw=True)
	get_issue(config, name)

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("write")

	updates = {k: fields[k] for k in ISSUE_EDITABLE_FIELDS if k in fields}
	unknown = set(fields) - set(ISSUE_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("Invalid Issue field(s): {0}").format(", ".join(sorted(unknown))))

	if "subject" in updates:
		subject = (updates["subject"] or "").strip()
		if not subject:
			frappe.throw(_("Subject is required"))
		updates["subject"] = subject

	if "project" in updates and updates["project"]:
		validate_project(config, updates["project"])

	for key, value in updates.items():
		doc.set(key, value)

	doc.save()
	return get_issue(config, name)


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
		"assignee_images": _user_images(assignees),
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
		"assignee_images": _user_images(assignees),
		"desk_url": f"/app/task/{doc.name}",
	}


def get_checklists(config: CockpitConfig, include_completed=0):
	"""Return Checklists linked to Issues/Tasks in this department scope."""
	frappe.has_permission("Checklist", "read", throw=True)
	department = _require_department(config)
	include_completed = frappe.utils.cint(include_completed)

	from phamos.api.checklist_inbox import _item_counts_map, _serialize_row

	issue_names = []
	or_filters = _issue_or_filters(config, department)
	if or_filters:
		issue_names = frappe.get_list(
			"Issue",
			or_filters=or_filters,
			pluck="name",
			limit_page_length=500,
		)

	task_names = frappe.get_list(
		"Task",
		filters={"department": department},
		pluck="name",
		limit_page_length=500,
	)

	if not issue_names and not task_names:
		return []

	filters_base = {}
	if not include_completed:
		filters_base["status"] = ("!=", "Completed")

	fields = [
		"name",
		"status",
		"completion_percentage",
		"document",
		"reference_record",
		"modified",
		"owner",
	]
	merged = {}

	if issue_names:
		for row in frappe.get_list(
			"Checklist",
			filters={**filters_base, "document": "Issue", "reference_record": ("in", issue_names)},
			fields=fields,
			order_by="modified desc",
			limit_page_length=200,
		):
			merged[row.name] = row

	if task_names:
		for row in frappe.get_list(
			"Checklist",
			filters={**filters_base, "document": "Task", "reference_record": ("in", task_names)},
			fields=fields,
			order_by="modified desc",
			limit_page_length=200,
		):
			merged[row.name] = row

	ordered = sorted(merged.values(), key=lambda r: r.modified or "", reverse=True)[:200]
	counts = _item_counts_map([r.name for r in ordered])
	return [_serialize_row(r, counts) for r in ordered]


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


def update_task(config: CockpitConfig, name, **fields):
	"""Update whitelisted Task fields within department scope."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(config, name)

	doc = frappe.get_doc("Task", name)
	doc.check_permission("write")

	updates = {k: fields[k] for k in TASK_EDITABLE_FIELDS if k in fields}
	unknown = set(fields) - set(TASK_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("Invalid Task field(s): {0}").format(", ".join(sorted(unknown))))

	if "subject" in updates:
		subject = (updates["subject"] or "").strip()
		if not subject:
			frappe.throw(_("Subject is required"))
		updates["subject"] = subject

	if "status" in updates:
		status = (updates["status"] or "").strip()
		if status not in TASK_KANBAN_STATUSES:
			frappe.throw(_("Invalid status: {0}").format(status))
		updates["status"] = status

	if "project" in updates and updates["project"]:
		validate_project(config, updates["project"])

	if "progress" in updates and updates["progress"] is not None:
		updates["progress"] = frappe.utils.flt(updates["progress"])

	for key, value in updates.items():
		doc.set(key, value)

	doc.save()
	return get_task(config, name)


def set_task_assignees(config: CockpitConfig, name, users=None):
	"""Replace Task assignees within department scope."""
	frappe.has_permission("Task", "write", throw=True)
	task = get_task(config, name)

	doc = frappe.get_doc("Task", name)
	doc.check_permission("write")

	desired = set(_parse_list(users))
	current = {a.get("owner") for a in get_assignments("Task", name)}

	for user in current - desired:
		remove_assignment("Task", name, user)

	to_add = list(desired - current)
	if to_add:
		add_assignment(
			{
				"doctype": "Task",
				"name": name,
				"assign_to": to_add,
				"description": doc.subject or task.get("subject"),
			}
		)

	return get_task(config, name)


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
