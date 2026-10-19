# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Create Accounting Receipts from uploaded files: PDFs and e-mails (.eml).

Rule: one receipt per PDF. An e-mail with three PDF invoices becomes three receipts.
An e-mail without a PDF (HTML receipts from shops and apps) becomes one receipt whose
PDF is rendered from the mail body, so preview, AI reading and DATEV work the same way.
"""

import os
import re
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr

import frappe
from erpnext import get_default_company
from frappe import _
from frappe.core.doctype.file.utils import get_content_hash
from frappe.utils import cstr, escape_html, strip_html
from frappe.utils.file_manager import save_file

DOCTYPE = "Accounting Receipt"
PDF_MAGIC = b"%PDF"
# Remote and active content is removed before an e-mail body is rendered to PDF, so the
# renderer never fetches URLs chosen by the sender.
UNSAFE_TAGS = re.compile(r"<(script|iframe|object|embed|link|img|video|audio|source)\b[^>]*>(.*?</\1>)?", re.I | re.S)


class IntakeError(frappe.ValidationError):
	pass


def create_receipts_from_file(filename, content, allow_duplicate=False):
	"""Create receipts from one uploaded file. Returns a list of result dicts:
	{"receipt", "title"} for created receipts, {"duplicate_of", "title"} for skipped ones.
	"""
	name = cstr(filename).strip() or "upload"
	lower = name.lower()
	if lower.endswith(".eml") or _looks_like_email(content):
		return _receipts_from_email(name, content, allow_duplicate)
	if lower.endswith(".pdf") or content[:4] == PDF_MAGIC:
		title = os.path.splitext(os.path.basename(name))[0] or name
		return [_receipt_with_pdf(title, name, content, frappe.session.user, allow_duplicate)]
	raise IntakeError(_("{0} is not a PDF or an e-mail (.eml).").format(name))


def _looks_like_email(content):
	head = content[:2000].lower()
	return b"\nsubject:" in head and (b"\nfrom:" in head or head.startswith(b"from:"))


def _receipts_from_email(filename, content, allow_duplicate):
	message = BytesParser(policy=policy.default).parsebytes(content)
	subject = cstr(message.get("subject")).strip() or os.path.splitext(filename)[0]
	sender = parseaddr(cstr(message.get("from")))[1] or frappe.session.user
	body_text, body_html = _email_body(message)

	pdfs = [(part_name, data) for part_name, data in _pdf_parts(message)]
	results = []
	if pdfs:
		for index, (pdf_name, data) in enumerate(pdfs):
			title = subject if len(pdfs) == 1 else f"{subject} – {os.path.splitext(pdf_name)[0]}"
			results.append(_receipt_with_pdf(title, pdf_name, data, sender, allow_duplicate))
	else:
		pdf = _render_email_pdf(subject, sender, message.get("date"), body_text, body_html)
		results.append(_receipt_with_pdf(subject, f"{_safe_filename(subject)}.pdf", pdf, sender, allow_duplicate))

	for result in results:
		if result.get("receipt"):
			save_file(_safe_filename(filename, ".eml"), content, DOCTYPE, result["receipt"], is_private=1)
			if body_text:
				frappe.get_doc(DOCTYPE, result["receipt"]).add_comment(
					"Comment", f"<p><b>{escape_html(_('E-mail from {0}').format(sender))}</b></p>"
					f"<pre style='white-space:pre-wrap'>{escape_html(body_text[:5000])}</pre>"
				)
	return results


def _pdf_parts(message):
	for part in message.walk():
		if part.is_multipart():
			continue
		part_name = cstr(part.get_filename())
		if part.get_content_type() == "application/pdf" or part_name.lower().endswith(".pdf"):
			data = part.get_payload(decode=True) or b""
			if data[:4] == PDF_MAGIC:
				yield (part_name or "attachment.pdf"), data


def _email_body(message):
	text = html = ""
	plain_part = message.get_body(preferencelist=("plain",))
	html_part = message.get_body(preferencelist=("html",))
	if plain_part:
		text = cstr(plain_part.get_content())
	if html_part:
		html = cstr(html_part.get_content())
		if not text:
			text = strip_html(html)
	return text.strip(), html


def _render_email_pdf(subject, sender, date, body_text, body_html):
	from frappe.utils.pdf import get_pdf

	meta = [(_("From"), sender), (_("Date"), cstr(date)), (_("Subject"), subject)]
	header = (
		"<p style='color:#555;font-size:11px'>"
		+ "<br>".join(f"{escape_html(label)}: {escape_html(value)}" for label, value in meta if value)
		+ "</p><hr>"
	)
	if body_html:
		body = UNSAFE_TAGS.sub("", body_html)
	else:
		body = f"<pre style='white-space:pre-wrap;font-family:Helvetica'>{escape_html(body_text)}</pre>"
	return get_pdf(f"<html><body style='font-family:Helvetica'>{header}{body}</body></html>")


def _receipt_with_pdf(title, pdf_name, pdf_content, uploaded_by, allow_duplicate):
	duplicate_of = None if allow_duplicate else find_duplicate(pdf_content)
	if duplicate_of:
		return {"title": title, "duplicate_of": duplicate_of}

	company = get_default_company()
	currency = (company and frappe.get_cached_value("Company", company, "default_currency")) or "EUR"
	receipt = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"title": title[:140],
			"company": company,
			"currency": currency,
			"conversion_rate": 1,
			"receipt_attached": "Yes",
			"uploaded_by": uploaded_by,
		}
	)
	receipt.insert()
	save_file(_safe_filename(pdf_name, ".pdf"), pdf_content, DOCTYPE, receipt.name, is_private=1)

	from phamos.phamos.doctype.accounting_receipt.accounting_receipt import _sync_attachment_field

	_sync_attachment_field(receipt.name)  # sets the attachment and queues the AI reading
	return {"title": receipt.title, "receipt": receipt.name}


def find_duplicate(content):
	"""Receipt (not cancelled) that already holds a file with exactly this content."""
	rows = frappe.get_all(
		"File",
		filters={"content_hash": get_content_hash(content), "attached_to_doctype": DOCTYPE},
		pluck="attached_to_name",
	)
	for name in rows:
		if frappe.db.get_value(DOCTYPE, name, "status") not in (None, "Cancelled"):
			return name
	return None


def _safe_filename(name, extension=""):
	base = re.sub(r"[^\w.\- ]+", "_", cstr(name)).strip(" ._") or "receipt"
	base = base[:120]
	if extension and not base.lower().endswith(extension):
		base += extension
	return base
