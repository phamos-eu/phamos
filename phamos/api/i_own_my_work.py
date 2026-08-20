# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.desk.form.load import get_assignments
from frappe.utils import get_fullname

ACTIVE_STATUSES = ("Open", "Replied", "On Hold", "Resolved")
ALLOWED_STATUSES = ("Open", "Replied", "On Hold", "Resolved", "Closed")
LIST_FIELDS = [
	"name",
	"subject",
	"status",
	"priority",
	"issue_type",
	"project",
	"custom_department",
	"owner",
	"raised_by",
	"modified",
	"creation",
	"opening_date",
	"_assign",
]


def check_app_permission():
	"""Show I Own My Work on the Apps screen for eligible users."""
	if frappe.session.user in (None, "Guest"):
		return False
	if frappe.session.user == "Administrator":
		return True

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False

	roles = set(frappe.get_roles())
	if roles & {"System Manager", "Ops User", "Support Team"}:
		return True

	return frappe.has_permission("Issue", ptype="read")


def _parse_list(value):
	if value is None or value == "":
		return []
	if isinstance(value, list):
		return value
	if isinstance(value, str):
		try:
			parsed = json.loads(value)
			return parsed if isinstance(parsed, list) else [value]
		except (TypeError, ValueError):
			return [u.strip() for u in value.split(",") if u.strip()]
	return []


def _parse_assignees(raw):
	if not raw:
		return []
	if isinstance(raw, list):
		return raw
	try:
		parsed = json.loads(raw)
		return parsed if isinstance(parsed, list) else []
	except (TypeError, ValueError):
		return []


def _user_label(user):
	if not user:
		return ""
	return get_fullname(user) or user


def _serialize_issue_row(row):
	assignees = _parse_assignees(row.get("_assign"))
	return {
		"name": row.get("name"),
		"subject": row.get("subject"),
		"status": row.get("status"),
		"priority": row.get("priority"),
		"issue_type": row.get("issue_type"),
		"project": row.get("project"),
		"department": row.get("custom_department"),
		"owner": row.get("owner"),
		"owner_name": _user_label(row.get("owner")),
		"raised_by": row.get("raised_by"),
		"modified": row.get("modified"),
		"creation": row.get("creation"),
		"opening_date": row.get("opening_date"),
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
	}


def _status_filters(include_closed):
	if include_closed:
		return []
	return [["status", "in", list(ACTIVE_STATUSES)]]


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return Issues for the current user: assigned | created."""
	frappe.has_permission("Issue", "read", throw=True)

	view = (view or "assigned").lower()
	include_closed = frappe.utils.cint(include_closed)
	user = frappe.session.user
	filters = _status_filters(include_closed)

	if view == "created":
		filters.append(["owner", "=", user])
		rows = frappe.get_list(
			"Issue",
			filters=filters,
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
			fields=LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=200,
		)

	return [_serialize_issue_row(r) for r in rows]


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail + assignees for the SPA."""
	frappe.has_permission("Issue", "read", throw=True)
	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")

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
		"desk_url": f"/app/issue/{doc.name}",
	}


@frappe.whitelist()
def get_form_options():
	"""Priorities, issue types, and active users for create/edit forms."""
	frappe.has_permission("Issue", "read", throw=True)

	priorities = frappe.get_all(
		"Issue Priority",
		fields=["name"],
		order_by="name asc",
	)
	issue_types = frappe.get_all(
		"Issue Type",
		fields=["name"],
		order_by="name asc",
	)
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("!=", "Guest")},
		fields=["name", "full_name"],
		order_by="full_name asc",
		limit_page_length=500,
	)
	departments = []
	if frappe.db.exists("DocType", "Department"):
		departments = frappe.get_all(
			"Department",
			filters={"disabled": 0} if frappe.get_meta("Department").has_field("disabled") else {},
			fields=["name"],
			order_by="name asc",
			limit_page_length=500,
		)
	projects = frappe.get_all(
		"Project",
		fields=["name", "project_name"],
		order_by="modified desc",
		limit_page_length=500,
	)
	return {
		"priorities": [p.name for p in priorities],
		"issue_types": [t.name for t in issue_types],
		"users": [{"name": u.name, "full_name": u.full_name or u.name} for u in users],
		"departments": [d.name for d in departments],
		"projects": [
			{"name": p.name, "project_name": p.project_name or p.name} for p in projects
		],
		"chat": get_chat_settings(),
	}


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
	"""Create an internal Issue and optionally assign users."""
	frappe.has_permission("Issue", "create", throw=True)

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	user = frappe.session.user
	user_email = frappe.db.get_value("User", user, "email") or user

	doc = frappe.get_doc(
		{
			"doctype": "Issue",
			"subject": subject,
			"description": description or "",
			"priority": priority or None,
			"issue_type": issue_type or None,
			"project": project or None,
			"raised_by": user_email,
			"status": "Open",
		}
	)
	if department and frappe.get_meta("Issue").has_field("custom_department"):
		doc.custom_department = department

	doc.insert()

	assignees = _parse_list(assign_to)
	if assignees:
		add_assignment(
			{
				"doctype": "Issue",
				"name": doc.name,
				"assign_to": assignees,
				"description": subject,
			}
		)

	return get_issue(doc.name)


@frappe.whitelist()
def update_status(name, status):
	"""Update Issue status (internal status set)."""
	frappe.has_permission("Issue", "write", throw=True)

	status = (status or "").strip()
	if status not in ALLOWED_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("write")
	doc.status = status
	doc.save()
	return get_issue(doc.name)


@frappe.whitelist()
def set_assignees(name, users=None):
	"""Replace Issue assignees with the given user list."""
	frappe.has_permission("Issue", "write", throw=True)

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("write")

	desired = set(_parse_list(users))
	current = {a.get("owner") for a in get_assignments("Issue", name)}

	for user in current - desired:
		remove_assignment("Issue", name, user)

	to_add = list(desired - current)
	if to_add:
		add_assignment(
			{
				"doctype": "Issue",
				"name": name,
				"assign_to": to_add,
				"description": doc.subject,
			}
		)

	# Keep Issue Raven channel members in sync with assignees (soft-dep)
	try:
		from phamos.api.issue_raven import sync_issue_channel_members

		sync_issue_channel_members(name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"Issue Raven member sync failed: {name}")

	return get_issue(name)


@frappe.whitelist()
def get_chat_settings():
	"""SPA soft-dependency flags for Issue Raven chat."""
	from phamos.api.issue_raven import get_chat_feature_flags

	return get_chat_feature_flags()


# Re-export Raven chat APIs for a stable SPA method prefix
from phamos.api.issue_raven import (  # noqa: E402, F401
	ensure_issue_channel,
	get_chat_messages,
	get_issue_chat,
	get_raven_users_for_invite,
	get_thread,
	invite_to_issue_channel,
	open_or_create_thread,
	send_chat_message,
)
