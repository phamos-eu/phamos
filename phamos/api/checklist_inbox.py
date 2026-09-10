# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Checklist inbox APIs for I Own My Work SPA."""

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, cstr

CHECKLIST_REFERENCE_DOCTYPES = ("Issue", "Task", "Project", "Lead", "Opportunity", "Customer")
TEMPLATE_DOCTYPE = "Checklist Template"


def _preview_fieldnames(doctype):
	meta = frappe.get_meta(doctype)
	return [
		field.fieldname
		for field in meta.fields
		if field.in_preview
		and field.fieldtype not in no_value_fields
		and field.fieldtype not in table_fields
	]


def _preview_cell(value, meta, fieldname):
	if value in (None, ""):
		return None
	field = meta.get_field(fieldname)
	if not field:
		return cstr(value)
	return f"{field.label}: {frappe.format(value, field, translated=True)}"


def _preview_line(value, meta, fieldname):
	if value in (None, ""):
		return None
	field = meta.get_field(fieldname)
	if not field:
		return {"label": fieldname, "value": cstr(value)}
	return {
		"label": field.label,
		"value": frappe.format(value, field, translated=True),
	}


def _template_picker_filters(document):
	template_filters = {"docstatus": 1}
	document = (document or "").strip()
	if document:
		template_filters["document"] = document
	return template_filters


def _template_search_or_filters(meta, preview_fields, txt, searchfield="name"):
	or_filters = [[searchfield, "like", f"%{txt}%"]]
	if searchfield != "title":
		or_filters.append(["title", "like", f"%{txt}%"])
	for fieldname in preview_fields:
		field = meta.get_field(fieldname)
		if field and field.fieldtype in {"Data", "Link", "Select", "Read Only"}:
			or_filters.append([fieldname, "like", f"%{txt}%"])
	return or_filters


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def checklist_owner_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: enabled System Users with Role = Employee."""
	from frappe.utils.user import get_users_with_role

	user_names = set(get_users_with_role("Employee") or [])
	user_names.discard("Guest")
	if not user_names:
		return []

	or_filters = [[searchfield, "like", f"%{txt}%"]]
	if searchfield == "name":
		or_filters += [[field, "like", f"%{txt}%"] for field in ("full_name", "first_name", "last_name")]

	return frappe.get_list(
		"User",
		filters={
			"name": ("in", list(user_names)),
			"enabled": 1,
			"user_type": ("!=", "Website User"),
		},
		fields=["name", "full_name"],
		limit_start=start,
		limit_page_length=page_len,
		order_by="full_name asc",
		or_filters=or_filters,
		as_list=True,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def checklist_template_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: submitted Checklist Templates, optionally filtered by Document."""
	frappe.has_permission("Checklist", "create", throw=True)
	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})

	meta = frappe.get_meta(TEMPLATE_DOCTYPE)
	preview_fields = _preview_fieldnames(TEMPLATE_DOCTYPE)
	document = (filters.get("document") or "").strip()
	template_filters = _template_picker_filters(document)
	or_filters = _template_search_or_filters(meta, preview_fields, txt, searchfield)

	list_fields = ["name", "title", *preview_fields]
	rows = frappe.get_list(
		TEMPLATE_DOCTYPE,
		filters=template_filters,
		fields=list_fields,
		limit_start=start,
		limit_page_length=page_len,
		order_by="title asc",
		or_filters=or_filters,
		ignore_permissions=True,
	)

	results = []
	for row in rows:
		item = [row.name, row.title or row.name]
		for fieldname in preview_fields:
			cell = _preview_cell(row.get(fieldname), meta, fieldname)
			if cell:
				item.append(cell)
		results.append(tuple(item))
	return results


@frappe.whitelist()
def get_checklist_template_picker_options(document, txt="", start=0, page_len=20):
	"""Structured options for SPA Checklist Template picker (submitted only)."""
	frappe.has_permission("Checklist", "create", throw=True)
	meta = frappe.get_meta(TEMPLATE_DOCTYPE)
	preview_fields = _preview_fieldnames(TEMPLATE_DOCTYPE)
	txt = (txt or "").strip()
	start = cint(start)
	page_len = cint(page_len) or 20

	template_filters = _template_picker_filters(document)
	or_filters = _template_search_or_filters(meta, preview_fields, txt) if txt else None

	list_fields = ["name", "title", *preview_fields]
	rows = frappe.get_list(
		TEMPLATE_DOCTYPE,
		filters=template_filters,
		fields=list_fields,
		limit_start=start,
		limit_page_length=page_len,
		order_by="title asc",
		or_filters=or_filters,
		ignore_permissions=True,
	)

	title_field = meta.title_field or "title"
	# Title is shown as the option heading; Document is already used as a list filter.
	picker_preview_fields = [
		fn for fn in preview_fields if fn not in {title_field, "document"}
	]

	options = []
	for row in rows:
		preview_lines = [{"label": _("ID"), "value": row.name}]
		for fieldname in picker_preview_fields:
			line = _preview_line(row.get(fieldname), meta, fieldname)
			if line:
				preview_lines.append(line)
		options.append(
			{
				"value": row.name,
				"title": row.title or row.name,
				"preview_lines": preview_lines,
			}
		)
	return options


@frappe.whitelist()
def get_checklist_template(name):
	"""Submitted template payload for SPA create dialog (snapshot preview)."""
	frappe.has_permission("Checklist", "create", throw=True)
	name = (name or "").strip()
	if not name:
		frappe.throw(_("Checklist Template is required"))

	row = frappe.db.get_value(
		"Checklist Template",
		{"name": name, "docstatus": 1},
		["name", "title", "document", "checklist_template_owner"],
		as_dict=True,
	)
	if not row:
		frappe.throw(_("Checklist Template not found or not submitted"))

	items = frappe.get_all(
		"Checklist Template Item",
		filters={"parent": name, "parenttype": "Checklist Template"},
		fields=["description", "note", "document", "record", "idx"],
		order_by="idx asc",
	)
	return {
		"name": row.name,
		"title": row.title or row.name,
		"document": row.document,
		"checklist_template_owner": row.checklist_template_owner,
		"items": [
			{
				"description": item.description or "",
				"note": item.note or "",
				"document": item.document,
				"record": item.record,
			}
			for item in items
		],
	}


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


def _item_counts_map(checklist_names):
	"""Batch-count checklist items for many parents (avoids N+1)."""
	counts = {name: (0, 0) for name in checklist_names}
	if not checklist_names:
		return counts
	rows = frappe.get_all(
		"Checklist Items",
		filters={"parent": ("in", list(checklist_names)), "parenttype": "Checklist"},
		fields=["parent", "done"],
		limit_page_length=0,
	)
	totals = {name: [0, 0] for name in checklist_names}
	for row in rows:
		parent = row.parent
		if parent not in totals:
			continue
		totals[parent][1] += 1
		if cint(row.done):
			totals[parent][0] += 1
	return {name: (done, total) for name, (done, total) in totals.items()}


def _item_counts(checklist_name):
	done, total = _item_counts_map([checklist_name]).get(checklist_name, (0, 0))
	return done, total


def _checklist_has_title_field():
	return frappe.get_meta("Checklist").has_field("title")


def _checklist_title_value(row_or_doc):
	if _checklist_has_title_field():
		return (getattr(row_or_doc, "title", None) or "").strip() or row_or_doc.name
	return row_or_doc.name


def _serialize_row(row, counts=None):
	if counts is None:
		done_count, total_count = _item_counts(row.name)
	else:
		done_count, total_count = counts.get(row.name, (0, 0))
	return {
		"name": row.name,
		"title": _checklist_title_value(row),
		"status": row.status,
		"completion_percentage": row.completion_percentage or 0,
		"document": row.document,
		"reference_record": row.reference_record,
		"modified": row.modified,
		"owner": row.owner,
		"done_count": done_count,
		"total_count": total_count,
		"desk_url": f"/app/checklist/{row.name}",
	}


@frappe.whitelist()
def get_checklist_inbox(include_completed=0):
	"""List Checklists visible to the current user."""
	frappe.has_permission("Checklist", "read", throw=True)
	include_completed = cint(include_completed)
	filters = {}
	if not include_completed:
		filters["status"] = ("!=", "Completed")

	fields = [
		"name",
		"status",
		"completion_percentage",
		"document",
		"reference_record",
		"modified",
		"owner",
	]
	if _checklist_has_title_field():
		fields.insert(1, "title")

	rows = frappe.get_list(
		"Checklist",
		filters=filters,
		fields=fields,
		order_by="modified desc",
		limit_page_length=200,
	)
	counts = _item_counts_map([r.name for r in rows])
	return [_serialize_row(r, counts) for r in rows]


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
				"description": row.description or "",
				"note": row.note or "",
				"document": row.document,
				"record": row.record,
			}
		)
	done_count = sum(1 for i in items if i["done"])
	return {
		"name": doc.name,
		"title": _checklist_title_value(doc),
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


@frappe.whitelist(methods=["POST"])
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

	_validate_reference_record(document, reference_record)

	fields = [
		"name",
		"status",
		"completion_percentage",
		"document",
		"reference_record",
		"modified",
		"owner",
	]
	if _checklist_has_title_field():
		fields.insert(1, "title")

	rows = frappe.get_list(
		"Checklist",
		filters={"document": document, "reference_record": reference_record},
		fields=fields,
		order_by="creation asc",
		limit_page_length=200,
	)
	counts = _item_counts_map([r.name for r in rows])
	return [_serialize_row(r, counts) for r in rows]


def _validate_reference_record(document, reference_record):
	document = (document or "").strip()
	reference_record = (reference_record or "").strip()
	if not document:
		frappe.throw(_("Document type is required"))
	if not reference_record:
		frappe.throw(_("Reference record is required"))
	if document not in CHECKLIST_REFERENCE_DOCTYPES:
		frappe.throw(_("Unsupported checklist reference type: {0}").format(document))
	if not frappe.db.exists(document, reference_record):
		frappe.throw(_("Reference record not found: {0}").format(reference_record))

	frappe.has_permission(document, "read", throw=True)
	frappe.get_doc(document, reference_record).check_permission("read")


def _resolve_checklist_title(name, document, reference_record):
	"""Resolve display title from SPA `name` arg or parent subject."""
	title = (name or "").strip()
	if not title and document == "Issue":
		title = (frappe.db.get_value("Issue", reference_record, "subject") or "").strip()
	if not title and document == "Task":
		title = (frappe.db.get_value("Task", reference_record, "subject") or "").strip()
	if not title:
		frappe.throw(_("Checklist title is required"))
	return title


def _unique_checklist_name(base_name):
	from frappe.model.naming import append_number_if_name_exists

	base_name = base_name.strip()
	return append_number_if_name_exists("Checklist", base_name)


def _parse_items(items):
	if items is None or items == "":
		return []
	if isinstance(items, str):
		items = frappe.parse_json(items)
	if not isinstance(items, list):
		frappe.throw(_("Invalid checklist items payload"))
	return items


@frappe.whitelist(methods=["POST"])
def create_spa_checklist(
	document,
	reference_record,
	name=None,
	items=None,
	checklist_owner=None,
	checklist_template=None,
):
	"""Create a Checklist linked to a parent document.

	`name` is the user-facing title from the SPA. On sites with Checklist.title
	+ naming_series, that value is stored in `title` and the series assigns `name`.
	On older prompt-named Checklists, it becomes the document name.
	"""
	frappe.has_permission("Checklist", "create", throw=True)

	document = (document or "").strip()
	reference_record = (reference_record or "").strip()
	_validate_reference_record(document, reference_record)

	template_name = (checklist_template or "").strip() or None
	if template_name:
		template_document = frappe.db.get_value(
			"Checklist Template",
			{"name": template_name, "docstatus": 1},
			"document",
		)
		if not template_document:
			frappe.throw(_("Checklist Template not found or not submitted"))
		if template_document != document:
			frappe.throw(
				_("Checklist Template Document must match {0}").format(document)
			)

	title = _resolve_checklist_title(name, document, reference_record)
	parsed_items = _parse_items(items)
	meta = frappe.get_meta("Checklist")
	owner = (checklist_owner or "").strip() or frappe.session.user

	doc = frappe.new_doc("Checklist")
	doc.document = document
	doc.reference_record = reference_record
	if meta.has_field("title"):
		doc.title = title
	else:
		doc.name = _unique_checklist_name(title)
	if meta.has_field("checklist_owner"):
		doc.checklist_owner = owner
	if template_name and meta.has_field("checklist_template"):
		doc.checklist_template = template_name

	for item in parsed_items:
		if not isinstance(item, dict):
			continue
		doc.append(
			"checklist_items",
			{
				"done": cint(item.get("done")),
				"description": item.get("description") or "",
				"note": item.get("note") or "",
				"document": item.get("document") or None,
				"record": item.get("record") or None,
			},
		)

	doc.insert()

	return get_checklist(doc.name)


@frappe.whitelist(methods=["POST"])
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
			"description": values.get("description") or "",
			"note": values.get("note") or "",
			"document": values.get("document") or None,
			"record": values.get("record") or None,
		},
	)
	doc.save()

	return get_checklist(checklist_name)


@frappe.whitelist(methods=["POST"])
def delete_spa_checklist_item(checklist_name, item_name):
	"""Remove a checklist item and return full SPA checklist payload."""
	doc = _require_checklist_write(checklist_name)
	item_name = (item_name or "").strip()
	if not item_name:
		frappe.throw(_("Checklist item is required"))

	row = next((r for r in doc.checklist_items if r.name == item_name), None)
	if not row:
		frappe.throw(_("Checklist item not found"))

	doc.remove(row)
	doc.save()
	return get_checklist(checklist_name)
