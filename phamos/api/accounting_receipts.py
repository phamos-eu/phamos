# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Cockpit receipt endpoints that are new in the receipt inbox work.

The older receipt endpoints still live in phamos.api.accounting_spa and move here step by step.
"""

import frappe
from frappe import _
from frappe.utils import cint

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
