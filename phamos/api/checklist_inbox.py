# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Checklist inbox APIs for I Own My Work SPA."""

import frappe
from frappe import _
from frappe.utils import cint


def _require_checklist_read(name):
	frappe.has_permission("Checklist", "read", throw=True)
	doc = frappe.get_doc("Checklist", name)
	doc.check_permission("read")
	return doc


def _require_checklist_write(name):
	frappe.has_permission("Checklist", "write", throw=True)
	doc = frappe.get_doc("Checklist", name)
	doc.check_permission("write")
	return doc


def _item_counts(checklist_name):
	rows = frappe.get_all(
		"Checklist Items",
		filters={"parent": checklist_name, "parenttype": "Checklist"},
		fields=["done"],
		limit_page_length=0,
	)
	total = len(rows)
	done = sum(1 for r in rows if cint(r.done))
	return done, total


def _serialize_row(row):
	done_count, total_count = _item_counts(row.name)
	return {
		"name": row.name,
		"status": row.status,
		"completion_percentage": row.completion_percentage or 0,
		"document": row.document,
		"reference_record": row.reference_record,
		"modified": row.modified,
		"owner": row.owner,
		"done_count": done_count,
		"total_count": total_count,
	}


@frappe.whitelist()
def get_checklist_inbox(include_completed=0):
	"""List Checklists visible to the current user."""
	frappe.has_permission("Checklist", "read", throw=True)
	include_completed = cint(include_completed)
	filters = {}
	if not include_completed:
		filters["status"] = ("!=", "Completed")

	rows = frappe.get_list(
		"Checklist",
		filters=filters,
		fields=[
			"name",
			"status",
			"completion_percentage",
			"document",
			"reference_record",
			"modified",
			"owner",
		],
		order_by="modified desc",
		limit_page_length=200,
	)
	return [_serialize_row(r) for r in rows]


@frappe.whitelist()
def get_checklist(name):
	"""Checklist detail + items for the SPA."""
	doc = _require_checklist_read(name)
	items = []
	for row in doc.checklist_items:
		items.append(
			{
				"name": row.name,
				"idx": row.idx,
				"done": cint(row.done),
				"note": row.note or "",
				"document": row.document,
				"record": row.record,
			}
		)
	done_count = sum(1 for i in items if i["done"])
	return {
		"name": doc.name,
		"status": doc.status,
		"completion_percentage": doc.completion_percentage or 0,
		"document": doc.document,
		"reference_record": doc.reference_record,
		"modified": doc.modified,
		"owner": doc.owner,
		"done_count": done_count,
		"total_count": len(items),
		"items": items,
		"desk_url": f"/app/checklist/{doc.name}",
	}


@frappe.whitelist()
def update_spa_checklist_item(checklist_name, item_name, values):
	"""Update a checklist item and return full SPA checklist payload."""
	_require_checklist_write(checklist_name)
	from phamos.phamos.doctype.checklist.checklist import update_checklist_item

	update_checklist_item(checklist_name, item_name, values)
	return get_checklist(checklist_name)


@frappe.whitelist()
def get_checklists_for_reference(document, reference_record):
	"""List Checklists linked to a parent document."""
	frappe.has_permission("Checklist", "read", throw=True)
	document = (document or "").strip()
	reference_record = (reference_record or "").strip()
	if not document or not reference_record:
		return []

	if not frappe.db.exists("DocType", document):
		frappe.throw(_("Invalid document type: {0}").format(document))
	if not frappe.db.exists(document, reference_record):
		frappe.throw(_("Reference record not found: {0}").format(reference_record))

	rows = frappe.get_list(
		"Checklist",
		filters={"document": document, "reference_record": reference_record},
		fields=[
			"name",
			"status",
			"completion_percentage",
			"document",
			"reference_record",
			"modified",
			"owner",
		],
		order_by="modified desc",
		limit_page_length=200,
	)
	return [_serialize_row(r) for r in rows]


def _validate_reference_record(document, reference_record):
	document = (document or "").strip()
	reference_record = (reference_record or "").strip()
	if not document:
		frappe.throw(_("Document type is required"))
	if not reference_record:
		frappe.throw(_("Reference record is required"))
	if not frappe.db.exists("DocType", document):
		frappe.throw(_("Invalid document type: {0}").format(document))
	if not frappe.db.exists(document, reference_record):
		frappe.throw(_("Reference record not found: {0}").format(reference_record))

	if document == "Issue":
		frappe.has_permission("Issue", "read", throw=True)
		frappe.get_doc("Issue", reference_record).check_permission("read")


def _resolve_checklist_name(name, document, reference_record):
	name = (name or "").strip()
	if not name and document == "Issue":
		name = (frappe.db.get_value("Issue", reference_record, "subject") or "").strip()
	if not name:
		frappe.throw(_("Checklist name is required"))
	return _unique_checklist_name(name)


def _unique_checklist_name(base_name):
	base_name = base_name.strip()
	if not frappe.db.exists("Checklist", base_name):
		return base_name

	counter = 2
	while frappe.db.exists("Checklist", f"{base_name} ({counter})"):
		counter += 1
	return f"{base_name} ({counter})"


def _parse_items(items):
	if items is None or items == "":
		return []
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not isinstance(items, list):
		frappe.throw(_("Invalid checklist items payload"))
	return items


@frappe.whitelist()
def create_spa_checklist(document, reference_record, name=None, items=None):
	"""Create a Checklist linked to a parent document."""
	frappe.has_permission("Checklist", "create", throw=True)

	document = (document or "").strip()
	reference_record = (reference_record or "").strip()
	_validate_reference_record(document, reference_record)

	name = _resolve_checklist_name(name, document, reference_record)
	parsed_items = _parse_items(items)

	doc = frappe.get_doc(
		{
			"doctype": "Checklist",
			"name": name,
			"document": document,
			"reference_record": reference_record,
		}
	)

	for item in parsed_items:
		if not isinstance(item, dict):
			continue
		doc.append(
			"checklist_items",
			{
				"done": cint(item.get("done")),
				"note": item.get("note") or "",
				"document": item.get("document") or None,
				"record": item.get("record") or None,
			},
		)

	doc.insert()

	return get_checklist(doc.name)


@frappe.whitelist()
def add_spa_checklist_item(checklist_name, values=None):
	"""Append a checklist item and return full SPA checklist payload."""
	doc = _require_checklist_write(checklist_name)

	if isinstance(values, str):
		values = frappe.parse_json(values)
	if not isinstance(values, dict):
		values = {}

	doc.append(
		"checklist_items",
		{
			"done": cint(values.get("done")),
			"note": values.get("note") or "",
			"document": values.get("document") or None,
			"record": values.get("record") or None,
		},
	)
	doc.save()

	return get_checklist(checklist_name)
