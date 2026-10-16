# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit receipt endpoints that are new in the receipt inbox work.

The older receipt endpoints still live in phamos.api.accounting_spa and move here step by step.
"""

import frappe
from frappe import _
from frappe.utils import cint, cstr, flt

from phamos.accounting.intake import IntakeError, create_receipts_from_file
from phamos.accounting.pdf_stamp import note_to_html, note_to_lines


@frappe.whitelist(methods=["POST"])
def create_receipts_from_upload():
	"""Called through /api/method/upload_file?method=... with one file (PDF or .eml).

	Returns {"results": [{"receipt", "title"} | {"duplicate_of", "title"}]}. A file whose
	content is already on a receipt is skipped unless allow_duplicate is set.
	"""
	frappe.has_permission("Accounting Receipt", "create", throw=True)
	content = frappe.local.uploaded_file
	filename = frappe.local.uploaded_filename
	if not content:
		frappe.throw(_("No file received."))
	try:
		results = create_receipts_from_file(
			filename, content, allow_duplicate=cint(frappe.form_dict.allow_duplicate)
		)
	except IntakeError as e:
		frappe.throw(str(e))
	return {"filename": filename, "results": results}


@frappe.whitelist(methods=["POST"])
def update_receipt_note(name, note=None):
	"""Save the note for the accounting office (printed on the PDF sent to DATEV)."""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	doc.note = note_to_html(note)
	doc.save()
	return {"name": doc.name, "note_text": "\n".join(note_to_lines(doc.note))}


def _latest_extraction(name):
	"""(run name, extraction analysis) of the latest completed AI run with an extraction."""
	runs = frappe.get_all(
		"AI Agent Run",
		filters={"reference_doctype": "Accounting Receipt", "reference_name": name, "status": "Completed"},
		fields=["name", "analysis"],
		order_by="creation desc",
		limit=5,
	)
	for run in runs:
		analysis = frappe.parse_json(run.analysis or "{}") or {}
		if analysis.get("extraction"):
			return run.name, analysis["extraction"]
	return None, None


def _same(current, extracted, fieldtype):
	if fieldtype in ("Currency", "Float", "Percent"):
		return abs(flt(current) - flt(extracted)) < 0.005
	return cstr(current).strip() == cstr(extracted).strip()


@frappe.whitelist()
def get_extraction_diff(name):
	"""What the AI read vs. what the receipt holds now, for accepting values one by one.

	Rows: {fieldname, label, fieldtype, current, extracted, state}; state is "new" (field is
	empty), "different" (field has another value) or "missing_link" (the AI found a supplier
	that does not exist yet). Equal values are left out.
	"""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")
	run, extraction = _latest_extraction(name)
	if not run:
		return {"run": None, "rows": [], "items": None}

	meta = frappe.get_meta("Accounting Receipt")
	rows = []
	values = extraction.get("values") or {}
	for fieldname, extracted in values.items():
		df = meta.get_field(fieldname)
		if not df or extracted in (None, ""):
			continue
		current = doc.get(fieldname)
		if current not in (None, "", 0) and _same(current, extracted, df.fieldtype):
			continue
		rows.append(
			{
				"fieldname": fieldname,
				"label": _(df.label),
				"fieldtype": df.fieldtype,
				"current": current,
				"extracted": extracted,
				"state": "new" if current in (None, "", 0) else "different",
			}
		)
	if extraction.get("supplier_name") and not values.get("supplier") and not doc.supplier:
		rows.append(
			{
				"fieldname": "supplier",
				"label": _("Supplier"),
				"fieldtype": "Link",
				"current": None,
				"extracted": extraction["supplier_name"],
				"state": "missing_link",
			}
		)
	items = extraction.get("items") or []
	items_differ = bool(items) and [r.get("item_name") for r in items] != [r.item_name for r in doc.items]
	return {
		"run": run,
		"rows": rows,
		"items": {"extracted": items, "current_count": len(doc.items)} if items_differ else None,
	}


@frappe.whitelist(methods=["POST"])
def apply_extraction(name, fields=None, include_items=0):
	"""Take over the AI's values for the chosen fields (and item lines). Saved as the
	current user, so the document history shows it as a human decision."""
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	run, extraction = _latest_extraction(name)
	if not run:
		frappe.throw(_("There is no AI reading for this receipt yet."))
	fields = frappe.parse_json(fields) if isinstance(fields, str) else (fields or [])
	values = extraction.get("values") or {}
	updated = []
	for fieldname in fields:
		if fieldname in values and doc.meta.get_field(fieldname):
			doc.set(fieldname, values[fieldname])
			updated.append(fieldname)
	if cint(include_items) and extraction.get("items"):
		doc.set("items", [])
		for row in extraction["items"]:
			doc.append("items", row)
		updated.append("items")
	if updated:
		doc.save()
	return {"updated": updated}
