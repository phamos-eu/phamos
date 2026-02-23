# Copyright (c) 2025, phamos.eu and contributors
# Copy Communication attachments to the reference document (e.g. Issue) so they appear in the sidebar.

import frappe
from frappe import _


def copy_attachments_to_reference_doc(doc, event=None):
	"""
	When a Communication has reference_doctype/reference_name (e.g. Issue created from email),
	copy each file attached to the Communication to the reference document so attachments
	show in the reference doc's sidebar (Attachments), not only in Activity.
	"""
	if not doc.reference_doctype or not doc.reference_name:
		return
	# Avoid copying for non-issue/linked docs if you want to limit scope
	# if doc.reference_doctype != "Issue":
	# 	return

	files = frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Communication",
			"attached_to_name": doc.name,
		},
		fields=["name", "file_name", "file_url", "is_private", "content_hash"],
	)
	if not files:
		return

	for f in files:
		# Already copied to reference?
		exists = frappe.db.exists(
			"File",
			{
				"attached_to_doctype": doc.reference_doctype,
				"attached_to_name": doc.reference_name,
				"file_url": f.file_url,
			},
		)
		if exists:
			continue

		try:
			file_doc = frappe.get_doc("File", f.name)
			new_file = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": file_doc.file_name,
					"file_url": file_doc.file_url,
					"is_private": file_doc.is_private or 0,
					"attached_to_doctype": doc.reference_doctype,
					"attached_to_name": doc.reference_name,
				}
			)
			new_file.insert(ignore_permissions=True)
			frappe.db.commit()
		except Exception:
			frappe.log_error(
				title=_("Copy Communication attachment to reference failed"),
				message=frappe.get_traceback(),
			)
			frappe.db.rollback()

	# When reference is Accounting Receipt, set its attachment field from first file
	if doc.reference_doctype == "Accounting Receipt" and doc.reference_name:
		try:
			from phamos.phamos.doctype.accounting_receipt.accounting_receipt import _sync_attachment_field
			_sync_attachment_field(doc.reference_name)
		except Exception:
			frappe.log_error(
				title=_("Sync Accounting Receipt attachment field failed"),
				message=frappe.get_traceback(),
			)
