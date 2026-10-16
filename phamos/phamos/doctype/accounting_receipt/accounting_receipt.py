# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from erpnext import get_default_company
from erpnext.setup.utils import get_exchange_rate
from frappe import _
from frappe.desk.form.load import get_attachments, get_communications
from frappe.model.document import Document
from frappe.utils import now, today
from frappe.utils.file_manager import get_file, save_file

SETTINGS_DOCTYPE = "phamos Settings"
# Statuses a successful DATEV send moves on to "Sent to DATEV". Paid and Cancelled stay.
STATUSES_ADVANCED_BY_DATEV_SEND = ("Inbox", "Needs Decision", "Approved to Pay", "Do Not Pay")


class AccountingReceipt(Document):
	def before_insert(self):
		self.sent_to_datev = 0
		self.datev_sent_by = None
		self.datev_sent_at = None
		self.datev_email_queue_ref = None
		if not self.status:
			self.status = "Inbox"

	def validate(self):
		"""
		Fetch and apply correct exchange rate based on posting_date
		and compute converted sum in company currency.
		"""
		if self.is_return:
			self.due_date = None
		if self.status != "Cancelled":
			self.cancel_reason = None
		self.set_item_accounts()

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

	def set_item_accounts(self):
		"""Lines with a category but no expense account take the category's account."""
		from phamos.accounting.categories import resolve_expense_account

		company = self.company or get_default_company()
		for row in self.get("items") or []:
			if row.item_code and not row.expense_account:
				row.expense_account = resolve_expense_account(row.item_code, company)

	@frappe.whitelist()
	def make_purchase_invoice(self):
		"""Create a draft Purchase Invoice from this receipt.

		The line amount is the timesheet total when time sheets were fetched (invoices from
		developers built from their hours), otherwise the receipt sum.
		"""
		self.check_permission("write")
		frappe.has_permission("Purchase Invoice", "create", throw=True)
		if self.get("items"):
			from phamos.accounting.branching import make_purchase_invoice

			return make_purchase_invoice(self)
		is_return = bool(self.is_return)

		pi = frappe.new_doc("Purchase Invoice")
		pi.company = self.company or get_default_company()
		if self.posting_date:
			pi.set_posting_time = 1
			pi.posting_date = self.posting_date
			pi.bill_date = self.posting_date
		pi.bill_no = self.supplier_reference
		pi.supplier = self.supplier
		pi.currency = self.currency
		pi.conversion_rate = self.conversion_rate
		pi.cost_center = self.cost_center
		pi.project = self.project
		if self.due_date and not is_return:
			pi.due_date = self.due_date
		pi.remarks = f"{self.title} ({self.name})"

		if is_return:
			pi.is_return = 1
			if self.return_against:
				original_pi = frappe.db.get_value(
					"Accounting Receipt", self.return_against, "purchase_invoice"
				)
				if original_pi:
					pi.return_against = original_pi

		amount = abs(self.total_billing_amount or self.sum or 0)
		pi.append(
			"items",
			{
				"item_code": self.item,
				"qty": -1 if is_return else 1,
				"rate": amount,
				"project": self.project,
				"cost_center": self.cost_center,
				"expense_account": self.payment_account,
			},
		)
		pi.set_missing_values()
		pi.insert()
		self.db_set("purchase_invoice", pi.name)
		return pi


@frappe.whitelist()
def make_accounting_receipt(issue):
	"""
		Create an Accouting Receipt from an Issue
	"""
	issue_doc = frappe.get_doc("Issue", issue)
	issue_doc.check_permission("write")
	ar = frappe.new_doc("Accounting Receipt")
	ar.posting_date = today()
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


def _first_attached_pdf(accounting_receipt_name):
	"""File URL of the first PDF attached to the receipt, or None.

	Non-PDF attachments (logos, signatures, .p7s, images) are ignored because preview,
	extraction and DATEV all need a PDF. Used both when filling the attachment field and
	when DATEV needs a fallback, so both pick the same file.
	"""
	return frappe.db.get_value(
		"File",
		filters={
			"attached_to_doctype": "Accounting Receipt",
			"attached_to_name": accounting_receipt_name,
			"file_url": ["like", "%.pdf"],
		},
		fieldname="file_url",
		order_by="creation asc",
	)


def _sync_attachment_field(accounting_receipt_name):
	"""Fill an empty attachment field with the first attached PDF and start extraction.

	An attachment that is already set is never replaced: it was chosen by a human or by an
	earlier sync, and replacing it would re-run extraction over the current values. New
	mails appended to the receipt therefore leave it alone.
	"""
	if frappe.db.get_value("Accounting Receipt", accounting_receipt_name, "attachment"):
		return
	first = _first_attached_pdf(accounting_receipt_name)
	if not first:
		return
	frappe.db.set_value("Accounting Receipt", accounting_receipt_name, "attachment", first)
	# The AI Accountant reads the new PDF in the background (fills empty fields only).
	try:
		from phamos.ai_agents.runner import enqueue_run

		enqueue_run("Accounting Receipt", accounting_receipt_name, trigger="Field Change")
	except Exception:
		frappe.log_error(title=_("Queue Accounting Receipt extraction failed"), message=frappe.get_traceback())


def sync_attachment_from_files(doc, event=None):
	"""Doc event: when Accounting Receipt has no attachment but has attached Files, set attachment from first file."""
	if doc.get("attachment"):
		return
	_sync_attachment_field(doc.name)


@frappe.whitelist()
def get_attached_files(accounting_receipt_name):
	"""Return the Files attached to an Accounting Receipt, newest first.

	Used by the form to fill the `pdf_attachment_choice` options. Querying File
	directly from the client (frappe.client.get_list) depends on File doctype
	permissions and fails with 403 for some users (phamos/phamos#1429). Instead,
	read access to the receipt is the gate: whoever can open the receipt may see
	its attachments, the same rule Frappe applies to the form sidebar.
	"""
	frappe.has_permission("Accounting Receipt", "read", doc=accounting_receipt_name, throw=True)
	return frappe.get_all(
		"File",
		filters={
			"attached_to_doctype": "Accounting Receipt",
			"attached_to_name": accounting_receipt_name,
		},
		fields=["file_name", "file_url"],
		order_by="creation desc",
		limit_page_length=50,
	)


def resolve_datev_recipient(doc):
	"""DATEV upload address for a receipt.

	The phamos Settings table decides: the row whose Receipt Types list the receipt's type,
	otherwise the default row. Sites whose table is still empty fall back to the address
	fields that used to live on every receipt.
	"""
	rows = frappe.get_all(
		"DATEV Recipient",
		filters={"parent": SETTINGS_DOCTYPE, "parenttype": SETTINGS_DOCTYPE},
		fields=["email", "receipt_types", "is_default"],
		order_by="idx asc",
	)
	receipt_type = (doc.receipt_type or "").strip().lower()
	if receipt_type:
		for row in rows:
			types = [t.strip().lower() for t in (row.receipt_types or "").split(",")]
			if receipt_type in types and row.email:
				return row.email
	for row in rows:
		if row.is_default and row.email:
			return row.email
	if rows:
		return None

	if doc.receipt_type not in ("", None, "Invoice", "Credit Note", "Receipt") and doc.get("datev_mail_recipient_2"):
		return doc.datev_mail_recipient_2
	return doc.get("datev_mail_recipient") or None


def _datev_pdf_url(doc):
	"""The PDF to send: the attachment field, else the first attached PDF."""
	if doc.attachment:
		return doc.attachment
	return _first_attached_pdf(doc.name)


DATEV_FILE_SUFFIX = "-DATEV.pdf"


def build_datev_pdf(doc, pdf_file_url):
	"""PDF that goes to DATEV: the original, or a stamped copy when the receipt has a note.

	The stamped copy is kept as an attachment "<receipt>-DATEV.pdf" (previous copies are
	replaced; Frappe may add a suffix to the stored name) so everyone can see what the
	accounting office received.
	Returns (attachment dict for frappe.sendmail, file_url of the stamped copy or None).
	"""
	from phamos.accounting.pdf_stamp import note_to_lines, stamp_pdf

	lines = note_to_lines(doc.note)
	if not lines:
		return {"file_url": pdf_file_url}, None
	try:
		_, original = get_file(pdf_file_url)
		stamped, _mode = stamp_pdf(original, doc.name, lines)
	except Exception:
		frappe.log_error(title=_("DATEV note could not be stamped"), message=frappe.get_traceback())
		return {"file_url": pdf_file_url}, None

	file_name = f"{doc.name}{DATEV_FILE_SUFFIX}"
	for old in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Accounting Receipt", "attached_to_name": doc.name, "file_name": ["like", f"{doc.name}-DATEV%.pdf"]},
		pluck="name",
	):
		frappe.delete_doc("File", old, ignore_permissions=True)
	saved = save_file(file_name, stamped, "Accounting Receipt", doc.name, is_private=1)
	return {"fname": file_name, "fcontent": stamped}, saved.file_url


@frappe.whitelist(methods=["POST"])
def preview_datev_pdf(accounting_receipt_name):
	"""Build the PDF DATEV would receive, without sending, and return its URL."""
	frappe.has_permission("Accounting Receipt", "write", doc=accounting_receipt_name, throw=True)
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
	pdf_file_url = _datev_pdf_url(doc)
	if not pdf_file_url or not pdf_file_url.lower().endswith(".pdf"):
		frappe.throw(_("PDF attachment is missing."))
	_attachment, stamped_url = build_datev_pdf(doc, pdf_file_url)
	return {"file_url": stamped_url or pdf_file_url, "stamped": bool(stamped_url)}


@frappe.whitelist()
def send_to_datev(accounting_receipt_name):
	"""
	Send Accounting Receipt PDF to DATEV via Email Queue.
	Returns: dict with ok=True/False, message, and optionally email_queue_name
	"""
	# Validate document exists
	if not frappe.db.exists("Accounting Receipt", accounting_receipt_name):
		return {"ok": False, "message": _("Accounting Receipt not found")}

	frappe.has_permission("Accounting Receipt", "write", doc=accounting_receipt_name, throw=True)
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)

	if doc.status == "Cancelled":
		return {"ok": False, "message": _("This receipt is cancelled and is not sent to DATEV.")}

	recipient = resolve_datev_recipient(doc)
	if not recipient:
		return {"ok": False, "message": _("DATEV recipient email is not configured. Please contact system administrator.")}

	pdf_file_url = _datev_pdf_url(doc)
	if pdf_file_url and not doc.attachment:
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

	# Prepare email subject and message
	subject = _("Accounting Receipt: {0}").format(doc.name)
	message = _("<p>Please find attached the accounting receipt for: <strong>{0}</strong></p>").format(doc.title or doc.name)

	# Send email via Frappe Email Queue
	try:
		attachment, _stamped_url = build_datev_pdf(doc, pdf_file_url)
		frappe.sendmail(
			recipients=[recipient],
			subject=subject,
			message=message,
			attachments=[attachment],
			reference_doctype="Accounting Receipt",
			reference_name=doc.name,
			send_after=None,
		)

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
		if doc.status in STATUSES_ADVANCED_BY_DATEV_SEND:
			doc.db_set("status", "Sent to DATEV")

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

	frappe.has_permission("Accounting Receipt", "read", doc=accounting_receipt_name, throw=True)
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
	pdf_url = _datev_pdf_url(doc)
	pdf_name = pdf_url.split("/")[-1] if pdf_url else None

	return {
		"ok": True,
		"recipient": resolve_datev_recipient(doc),
		"pdf_name": pdf_name,
		"pdf_url": pdf_url,
		"already_sent": doc.sent_to_datev,
		"sent_at": doc.datev_sent_at,
		"sent_by": doc.datev_sent_by,
		"email_queue_ref": doc.datev_email_queue_ref
	}
