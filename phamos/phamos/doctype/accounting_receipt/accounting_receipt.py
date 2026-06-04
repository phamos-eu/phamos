# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today, now
from erpnext import get_default_company
from frappe.desk.form.load import get_attachments, get_communications
from frappe.desk.form.utils import add_comment


class AccountingReceipt(Document):
	def before_insert(self):
		self.sent_to_datev = 0
		self.datev_sent_by = None
		self.datev_sent_at = None
		self.datev_email_queue_ref = None
	def validate(self):
		"""
		Fetch and apply correct exchange rate based on posting_date
		and compute converted sum in company currency.
		"""
		if self.is_return:
			self.due_date = None

		company = self.company or get_default_company()
		if not company or not self.currency:
			return
		company_currency = frappe.db.get_value("Company", company, "default_currency")
		if not company_currency:
			return
		if company_currency == self.currency:
			# Same currency: ensure conversion_rate is 1 and base sum equals sum
			self.conversion_rate = 1
			if self.sum:
				self.sum_in_company_currency = self.sum
			return
		# Fetch exchange rate for date
		try:
			rate = get_exchange_rate(self.currency, company_currency, self.posting_date or today())
		except Exception:
			rate = None
		if rate:
			self.conversion_rate = rate
			if self.sum:
				self.sum_in_company_currency = float(self.sum) * float(rate)

	@frappe.whitelist()
	def make_purchase_invoice(self):
		"""
			Create a Purchase Invoice from Accounting Receipt
		"""
		is_return = bool(self.is_return)

		pi = frappe.new_doc("Purchase Invoice")
		pi.posting_date = today()
		company = get_default_company()
		pi.company = company
		pi.supplier = self.supplier
		pi.currency = self.currency
		pi.exchange_rate = self.conversion_rate
		pi.expense_account = self.payment_account

		if is_return:
			pi.is_return = 1
			if self.return_against:
				original_pi = frappe.db.get_value(
					"Accounting Receipt", self.return_against, "purchase_invoice"
				)
				if original_pi:
					pi.return_against = original_pi

		pi.append(
			"items",
			{
				"item_code": self.item,
				"qty": -1 if is_return else 1,
				"rate": abs(self.total_billing_amount or 0),
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
	"""Set Accounting Receipt's attachment field from first attached PDF, if available.

	We intentionally ignore non-PDF attachments (logos, signatures, .p7s, images, etc.)
	because downstream flows (preview, extraction, DATEV) expect a PDF.
	"""
	first = frappe.db.get_value(
		"File",
		filters={
			"attached_to_doctype": "Accounting Receipt",
			"attached_to_name": accounting_receipt_name,
			"file_url": ["like", "%.pdf"],
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


@frappe.whitelist()
def send_to_datev(accounting_receipt_name):
	"""
	Send Accounting Receipt PDF to DATEV via Email Queue.
	Returns: dict with ok=True/False, message, and optionally email_queue_name
	"""
	# Validate document exists
	if not frappe.db.exists("Accounting Receipt", accounting_receipt_name):
		return {"ok": False, "message": _("Accounting Receipt not found")}
	
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
	
	# Determine recipient based on receipt_type
	recipient = None
	if doc.receipt_type == "Sonstiges" and doc.datev_mail_recipient_2:
		recipient = doc.datev_mail_recipient_2
	elif doc.datev_mail_recipient:
		recipient = doc.datev_mail_recipient
	
	if not recipient:
		return {"ok": False, "message": _("DATEV recipient email is not configured. Please contact system administrator.")}
	
	# Check if PDF attachment exists in the attachment field or in attached files
	pdf_file_url = doc.attachment
	
	# If attachment field is empty, try to find a PDF in attached files
	if not pdf_file_url:
		attached_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Accounting Receipt",
				"attached_to_name": doc.name,
				"file_url": ["like", "%.pdf"]
			},
			fields=["file_url"],
			order_by="creation desc",
			limit=1
		)
		if attached_files:
			pdf_file_url = attached_files[0].file_url
			# Auto-sync to attachment field for future reference
			doc.db_set("attachment", pdf_file_url, update_modified=False)
	
	# Final check
	if not pdf_file_url or not pdf_file_url.lower().endswith(".pdf"):
		return {
			"ok": False, 
			"message": _("PDF attachment is missing. Please attach a PDF file using the 'Attachment' field or the Attachments sidebar (📎).")
		}
	
	# Check for duplicate sends - warn if already sent to same recipient
	if doc.sent_to_datev and doc.datev_email_queue_ref:
		# Check if there's a successful email in queue
		existing_email = frappe.db.get_value(
			"Email Queue",
			doc.datev_email_queue_ref,
			["name", "status"],
			as_dict=True
		)
		if existing_email and existing_email.status in ["Sent", "Not Sent", "Sending"]:
			return {
				"ok": False,
				"message": _("This document was already sent to DATEV on {0} by {1}. Email Queue: {2}").format(
					frappe.format(doc.datev_sent_at, {"fieldtype": "Datetime"}),
					doc.datev_sent_by,
					doc.datev_email_queue_ref
				),
				"is_duplicate": True
			}
	
	# Use the PDF file URL we found/validated earlier
	file_url = pdf_file_url
	
	# Prepare email subject and message
	subject = _("Accounting Receipt: {0}").format(doc.name)
	message = _("<p>Please find attached the accounting receipt for: <strong>{0}</strong></p>").format(doc.title or doc.name)
	
	# Send email via Frappe Email Queue
	try:
		email_args = {
			"recipients": [recipient],
			"subject": subject,
			"message": message,
			"attachments": [{
				"file_url": file_url
			}],
			"reference_doctype": "Accounting Receipt",
			"reference_name": doc.name,
			"send_after": None,
		}
		
		# Queue the email
		frappe.sendmail(**email_args)
		
		# Get the email queue name (last created for this doc)
		email_queue_name = frappe.db.get_value(
			"Email Queue",
			filters={
				"reference_doctype": "Accounting Receipt",
				"reference_name": doc.name
			},
			fieldname="name",
			order_by="creation desc"
		)
		
		# Update Accounting Receipt with sent status and audit trail
		doc.db_set("sent_to_datev", 1, update_modified=False)
		doc.db_set("datev_sent_by", frappe.session.user, update_modified=False)
		doc.db_set("datev_sent_at", now(), update_modified=False)
		if email_queue_name:
			doc.db_set("datev_email_queue_ref", email_queue_name, update_modified=False)
		
		return {
			"ok": True,
			"message": _("Email queued successfully to {0}").format(recipient),
			"email_queue_name": email_queue_name,
			"recipient": recipient
		}
		
	except Exception as e:
		frappe.log_error(title=_("DATEV Email Send Failed"), message=frappe.get_traceback())
		return {
			"ok": False,
			"message": _("Failed to queue email: {0}").format(str(e))
		}


@frappe.whitelist()
def get_datev_send_info(accounting_receipt_name):
	"""
	Get information needed for the DATEV send confirmation dialog.
	Returns: dict with recipient, pdf_name, already_sent, etc.
	"""
	if not frappe.db.exists("Accounting Receipt", accounting_receipt_name):
		return {"ok": False, "message": _("Accounting Receipt not found")}
	
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
	
	# Determine recipient
	recipient = None
	if doc.receipt_type == "Sonstiges" and doc.datev_mail_recipient_2:
		recipient = doc.datev_mail_recipient_2
	elif doc.datev_mail_recipient:
		recipient = doc.datev_mail_recipient
	
	# Get PDF - check attachment field first, then attached files
	pdf_url = doc.attachment
	if not pdf_url:
		# Try to find PDF in attached files
		attached_files = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": "Accounting Receipt",
				"attached_to_name": doc.name,
				"file_url": ["like", "%.pdf"]
			},
			fields=["file_url"],
			order_by="creation desc",
			limit=1
		)
		if attached_files:
			pdf_url = attached_files[0].file_url
	
	pdf_name = pdf_url.split("/")[-1] if pdf_url else None
	
	return {
		"ok": True,
		"recipient": recipient,
		"pdf_name": pdf_name,
		"pdf_url": pdf_url,
		"already_sent": doc.sent_to_datev,
		"sent_at": doc.datev_sent_at,
		"sent_by": doc.datev_sent_by,
		"email_queue_ref": doc.datev_email_queue_ref
	}
