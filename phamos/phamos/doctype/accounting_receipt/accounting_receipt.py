# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today
from erpnext import get_default_company
from frappe.desk.form.load import get_attachments, get_communications
from frappe.desk.form.utils import add_comment


class AccountingReceipt(Document):
	@frappe.whitelist()
	def make_purchase_invoice(self):
		"""
			Create a Purchase Invoice from Accounting Receipt
		"""
		pi = frappe.new_doc("Purchase Invoice")
		pi.posting_date = today()
		company = get_default_company()
		pi.company = company
		pi.supplier = self.supplier
		pi.currency = self.currency
		pi.exchange_rate = self.conversion_rate
		pi.expense_account = self.payment_account
		pi.append(
			"items",
			{
				"item_code": self.item,
				"qty": 1,
				"rate": self.total_billing_amount,
				"project": self.project,
				"expense_account": self.payment_account
			},
		)
		pi.set_missing_values()
		pi.insert()
		self.db_set('purchase_invoice', pi.name)
		return pi


@frappe.whitelist()
def make_accounting_receipt(issue):
	"""
		Create an Accouting Receipt from an Issue
	"""
	issue_doc = frappe.get_doc("Issue",issue)
	ar = frappe.new_doc("Accounting Receipt")
	ar.posting_date = today()
	ar.customer = issue_doc.customer
	ar.project = issue_doc.project
	ar.title = issue_doc.subject
	ar.conversion_rate = 1
	ar.insert()
	issue_doc.db_set("accounting_receipt", ar.name)

	""" Get the email data and attachments """
	communication_data = get_communications("Issue", issue)
	for data in communication_data:
		content = data.content
		""" Transfer the attachments """
		if attachments := [d.name for d in get_attachments("Communication", data.name)]:
			for attachment in attachments:
				file_doc = frappe.get_doc("File", attachment)
				file_doc.db_set("attached_to_doctype", "Accounting Receipt")
				file_doc.db_set("attached_to_name", ar.name)
		""" Add email as Comment """
		ar.add_comment("Comment", content)

	""" Set doc-level attachment field from first attached file if any """
	_sync_attachment_field(ar.name)
	return ar.name


def _sync_attachment_field(accounting_receipt_name):
	"""Set Accounting Receipt's attachment field from first File attached to it, if field is empty."""
	first = frappe.db.get_value(
		"File",
		filters={
			"attached_to_doctype": "Accounting Receipt",
			"attached_to_name": accounting_receipt_name,
		},
		fieldname="file_url",
		order_by="creation asc",
	)
	if first:
		frappe.db.set_value("Accounting Receipt", accounting_receipt_name, "attachment", first)
		# Auto-extract from PDF (runs in background; no on_update when we only db_set)
		try:
			from phamos.phamos.doctype.accounting_receipt.mistral_pdf import extract_from_pdf_and_update_ar
			frappe.enqueue(
				extract_from_pdf_and_update_ar,
				queue="default",
				timeout=300,
				accounting_receipt_name=accounting_receipt_name,
				enqueue_after_commit=True,
			)
		except Exception:
			pass


def sync_attachment_from_files(doc, event=None):
	"""Doc event: when Accounting Receipt has no attachment but has attached Files, set attachment from first file."""
	if doc.get("attachment"):
		return
	_sync_attachment_field(doc.name)
