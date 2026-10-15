# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""ToDos of the session user for the Personal Cockpit (phamos/phamos#1541).

A ToDo is both a standalone reminder and the row behind every assignment, so
"my ToDos" are all ToDos allocated to me, with or without a reference. Writes
go through the Document API: Frappe's ToDo controller then keeps `_assign` on
the referenced record in sync and its own permission rules apply.
"""

import re

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, strip_html, today

from phamos.api.issue_common import _user_label

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}
OPEN_STATUSES = ("Open",)
TODO_FIELDS = [
	"name",
	"description",
	"date",
	"priority",
	"status",
	"reference_type",
	"reference_name",
	"assigned_by",
	"creation",
	"modified",
]
# Reference types offered in the "New ToDo" dialog; others stay readable when Desk set them.
CREATE_REFERENCE_TYPES = (
	"Issue",
	"Task",
	"Project",
	"Implementation",
	"Customer",
	"Lead",
	"Opportunity",
	"Contact",
)
SUMMARY_LENGTH = 140


BLOCK_END = re.compile(r"</(p|div|li|h[1-6]|blockquote|pre)>|<br\s*/?>", re.IGNORECASE)


def _summary(description):
	"""First non-empty line of the (HTML) description, shortened."""
	text = strip_html(BLOCK_END.sub("\n", description or "")).strip()
	first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
	if len(first_line) > SUMMARY_LENGTH:
		return first_line[: SUMMARY_LENGTH - 1].rstrip() + "…"
	return first_line


def _desk_url(doctype, name):
	if not doctype or not name:
		return None
	return f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}"


def _reference_titles(rows):
	"""Map (reference_type, reference_name) -> title, one query per reference type."""
	by_type = {}
	for row in rows:
		if row.get("reference_type") and row.get("reference_name"):
			by_type.setdefault(row["reference_type"], set()).add(row["reference_name"])

	titles = {}
	for doctype, names in by_type.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		title_field = frappe.get_meta(doctype).get_title_field()
		if not title_field or title_field == "name":
			continue
		for name, title in frappe.get_all(
			doctype,
			filters={"name": ("in", list(names))},
			fields=["name", title_field],
			as_list=True,
		):
			titles[(doctype, name)] = title
	return titles


def _serialize(row, titles):
	reference_type = row.get("reference_type")
	reference_name = row.get("reference_name")
	date = row.get("date")
	return {
		"name": row.get("name"),
		"description": row.get("description") or "",
		"summary": _summary(row.get("description")),
		"date": date,
		"overdue": bool(date and row.get("status") == "Open" and getdate(date) < getdate(today())),
		"priority": row.get("priority"),
		"status": row.get("status"),
		"reference_type": reference_type,
		"reference_name": reference_name,
		"reference_title": titles.get((reference_type, reference_name)),
		"reference_url": _desk_url(reference_type, reference_name),
		"assigned_by": row.get("assigned_by"),
		"assigned_by_name": _user_label(row.get("assigned_by")),
		"creation": row.get("creation"),
		"modified": row.get("modified"),
		"desk_url": _desk_url("ToDo", row.get("name")),
	}


def sort_key(row):
	"""Due date ascending with undated last, then High, Medium, Low, then oldest first."""
	date = row.get("date")
	return (
		date is None,
		getdate(date) if date else getdate("1900-01-01"),
		PRIORITY_ORDER.get(row.get("priority"), len(PRIORITY_ORDER)),
		get_datetime(row.get("creation")) if row.get("creation") else get_datetime("1900-01-01"),
	)


def _get_my_todo(name):
	doc = frappe.get_doc("ToDo", name)
	if doc.allocated_to != frappe.session.user:
		frappe.throw(_("This ToDo is not yours."), frappe.PermissionError)
	return doc


def _validate_date(date):
	if date and getdate(date) < getdate(today()):
		frappe.throw(_("The due date cannot be in the past."))


def get_my_todos(include_closed=0):
	"""Return my ToDos: open ones, plus Closed ones when asked; never Cancelled."""
	statuses = ["Open", "Closed"] if cint(include_closed) else list(OPEN_STATUSES)
	rows = frappe.get_list(
		"ToDo",
		filters={"allocated_to": frappe.session.user, "status": ("in", statuses)},
		fields=TODO_FIELDS,
		limit_page_length=0,
	)
	titles = _reference_titles(rows)
	return [_serialize(row, titles) for row in sorted(rows, key=sort_key)]


def get_todo(name):
	doc = _get_my_todo(name)
	row = doc.as_dict()
	return _serialize(row, _reference_titles([row]))


def get_reference_types():
	"""Reference types the "New ToDo" dialog offers (the installed ones the user can read)."""
	return [
		doctype
		for doctype in CREATE_REFERENCE_TYPES
		if frappe.db.exists("DocType", doctype) and frappe.has_permission(doctype, "read")
	]


def create_todo(description, date=None, priority=None, reference_type=None, reference_name=None):
	"""Create a ToDo for me, optionally referencing a record I can read."""
	description = (description or "").strip()
	if not strip_html(description).strip():
		frappe.throw(_("Description is required"))
	_validate_date(date)

	if priority and priority not in PRIORITY_ORDER:
		frappe.throw(_("Invalid priority: {0}").format(priority))

	if bool(reference_type) != bool(reference_name):
		frappe.throw(_("Select both the reference type and the record, or neither."))
	if reference_type:
		if reference_type not in CREATE_REFERENCE_TYPES:
			frappe.throw(_("{0} cannot be referenced here.").format(reference_type))
		frappe.get_doc(reference_type, reference_name).check_permission("read")

	doc = frappe.get_doc(
		{
			"doctype": "ToDo",
			"description": description,
			"date": date or None,
			"priority": priority or "Medium",
			"status": "Open",
			"allocated_to": frappe.session.user,
			"assigned_by": frappe.session.user,
			"reference_type": reference_type or None,
			"reference_name": reference_name or None,
		}
	)
	doc.insert()
	return get_todo(doc.name)


def update_todo(name, description=None, date=None, priority=None, modified=None):
	"""Update description, due date or priority of one of my ToDos.

	The reference is read-only here. A due date may only be moved to today or later;
	an overdue ToDo keeps its date until it is changed.
	"""
	doc = _get_my_todo(name)
	doc.check_permission("write")

	if description is not None:
		if not strip_html(description).strip():
			frappe.throw(_("Description is required"))
		doc.description = description
	if date is not None:
		date = date or None
		if date != (str(doc.date) if doc.date else None):
			_validate_date(date)
		doc.date = date
	if priority is not None:
		if priority not in PRIORITY_ORDER:
			frappe.throw(_("Invalid priority: {0}").format(priority))
		doc.priority = priority

	if modified:
		doc.modified = get_datetime(modified)
	doc.save()
	return get_todo(doc.name)


def set_status(name, status):
	"""Close (done) or reopen one of my ToDos.

	Saving the ToDo runs Frappe's update_in_reference, so closing one that belongs to an
	assignment removes me from `_assign` on that record, and reopening adds me back.
	"""
	if status not in ("Open", "Closed"):
		frappe.throw(_("Invalid status: {0}").format(status))
	doc = _get_my_todo(name)
	doc.check_permission("write")
	if doc.status != status:
		doc.status = status
		doc.save()
	return get_todo(doc.name)
