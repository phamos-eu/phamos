# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue helpers shared by every cockpit API.

Nothing here is whitelisted: each cockpit exposes scoped wrappers
(phamos.api.department_cockpit and the per-cockpit modules) that check
the cockpit's scope before calling these.
"""

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
	"description",
	"_assign",
]


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
		"description": row.get("description") or "",
		"checklist_search": row.get("checklist_search") or "",
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
	}


def _checklist_search_by_issue(issue_names):
	"""Map Issue name -> plain text from linked checklist titles and item notes."""
	if not issue_names:
		return {}

	checklists = frappe.get_all(
		"Checklist",
		filters={"document": "Issue", "reference_record": ("in", list(issue_names))},
		fields=["name", "reference_record"],
		limit_page_length=0,
	)
	if not checklists:
		return {}

	blobs = {name: [] for name in issue_names}
	checklist_to_issue = {}
	for row in checklists:
		issue_name = row.reference_record
		if issue_name not in blobs:
			continue
		checklist_to_issue[row.name] = issue_name
		blobs[issue_name].append(row.name)

	checklist_names = list(checklist_to_issue.keys())
	if checklist_names:
		items = frappe.get_all(
			"Checklist Items",
			filters={"parent": ("in", checklist_names), "parenttype": "Checklist"},
			fields=["parent", "note"],
			limit_page_length=0,
		)
		for item in items:
			issue_name = checklist_to_issue.get(item.parent)
			if not issue_name:
				continue
			note = frappe.utils.strip_html(item.note or "").strip()
			if note:
				blobs[issue_name].append(note)

	return {name: " ".join(parts) for name, parts in blobs.items() if parts}


def enrich_issue_rows_for_search(rows):
	"""Attach checklist search text to serialized or raw issue rows, then serialize."""
	serialized = [_serialize_issue_row(r) for r in rows]
	search_map = _checklist_search_by_issue([r["name"] for r in serialized if r.get("name")])
	for row in serialized:
		row["checklist_search"] = search_map.get(row["name"], "")
	return serialized

def _status_filters(include_closed):
	if include_closed:
		return []
	return [["status", "in", list(ACTIVE_STATUSES)]]



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
		"modified_by": doc.modified_by,
		"modified_by_name": _user_label(doc.modified_by),
		"creation": doc.creation,
		"opening_date": getattr(doc, "opening_date", None),
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
		"desk_url": f"/app/issue/{doc.name}",
	}


def get_form_options(project_filters=None):
	"""Priorities, issue types, departments and projects for create/edit forms.

	`project_filters` narrows the Project list (the Personal Cockpit passes open
	projects only); department cockpits narrow it further themselves.
	"""
	frappe.has_permission("Issue", "read", throw=True)

	priorities = frappe.get_all("Issue Priority", fields=["name"], order_by="name asc")
	issue_types = frappe.get_all("Issue Type", fields=["name"], order_by="name asc")
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
		filters=project_filters or {},
		fields=["name", "project_name"],
		order_by="modified desc",
		limit_page_length=500,
	)
	return {
		"priorities": [p.name for p in priorities],
		"issue_types": [t.name for t in issue_types],
		"departments": [d.name for d in departments],
		"projects": [{"name": p.name, "project_name": p.project_name or p.name} for p in projects],
	}


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

	return get_issue(name)
