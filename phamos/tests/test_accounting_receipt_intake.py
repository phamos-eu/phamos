# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Receipts from dropped PDFs and e-mails, and the DATEV note stamp."""

import io
from email.message import EmailMessage
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from pypdf import PdfReader, PdfWriter

from phamos.accounting import intake
from phamos.accounting.pdf_stamp import note_to_html, note_to_lines, stamp_pdf
from phamos.phamos.doctype.accounting_receipt import accounting_receipt as ar_module
from phamos.phamos.doctype.accounting_receipt.data_extract import get_extractable_fields_meta


def blank_pdf(pages=1, width=595, height=842, marker=""):
	writer = PdfWriter()
	for _ in range(pages):
		writer.add_blank_page(width=width, height=height)
	writer.add_metadata({"/Title": marker or frappe.generate_hash()})  # unique content per call
	out = io.BytesIO()
	writer.write(out)
	return out.getvalue()


def email_bytes(subject="Ihre Rechnung", sender="Billing <billing@supplier.test>", pdfs=(), html=None, text="Hallo"):
	msg = EmailMessage()
	msg["Subject"] = subject
	msg["From"] = sender
	msg["To"] = "rechnungen@phamos.eu"
	msg.set_content(text)
	if html:
		msg.add_alternative(html, subtype="html")
	for name, data in pdfs:
		msg.add_attachment(data, maintype="application", subtype="pdf", filename=name)
	return msg.as_bytes()


def files_of(receipt):
	return frappe.get_all(
		"File", filters={"attached_to_doctype": "Accounting Receipt", "attached_to_name": receipt}, pluck="file_name"
	)


class TestReceiptIntake(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.enqueue = patch.object(ar_module.frappe, "enqueue").start()

	def tearDown(self):
		patch.stopall()
		frappe.db.rollback()

	def test_pdf_becomes_one_receipt_and_is_queued_for_the_ai(self):
		results = intake.create_receipts_from_file("Telekom Oktober.pdf", blank_pdf())
		self.assertEqual(len(results), 1)
		doc = frappe.get_doc("Accounting Receipt", results[0]["receipt"])
		self.assertEqual(doc.title, "Telekom Oktober")
		self.assertEqual(doc.status, "Inbox")
		self.assertTrue(doc.attachment.endswith(".pdf"))
		self.assertEqual(doc.uploaded_by, "Administrator")
		self.enqueue.assert_called_once()

	def test_same_pdf_twice_is_a_duplicate_unless_forced(self):
		pdf = blank_pdf()
		first = intake.create_receipts_from_file("a.pdf", pdf)[0]["receipt"]
		again = intake.create_receipts_from_file("a copy.pdf", pdf)[0]
		self.assertEqual(again.get("duplicate_of"), first)
		self.assertNotIn("receipt", again)
		forced = intake.create_receipts_from_file("a copy.pdf", pdf, allow_duplicate=True)[0]
		self.assertIn("receipt", forced)

	def test_cancelled_receipt_does_not_block_a_new_upload(self):
		pdf = blank_pdf()
		first = intake.create_receipts_from_file("a.pdf", pdf)[0]["receipt"]
		frappe.db.set_value("Accounting Receipt", first, {"status": "Cancelled", "cancel_reason": "Other"})
		self.assertIn("receipt", intake.create_receipts_from_file("a.pdf", pdf)[0])

	def test_email_with_two_pdfs_becomes_two_receipts(self):
		raw = email_bytes(subject="Rechnungen Oktober", pdfs=[("R-1.pdf", blank_pdf()), ("R-2.pdf", blank_pdf())])
		results = intake.create_receipts_from_file("Rechnungen Oktober.eml", raw)
		names = [r["receipt"] for r in results]
		self.assertEqual(len(names), 2)
		titles = sorted(frappe.db.get_value("Accounting Receipt", n, "title") for n in names)
		self.assertEqual(titles, ["Rechnungen Oktober – R-1", "Rechnungen Oktober – R-2"])
		for name in names:
			self.assertEqual(frappe.db.get_value("Accounting Receipt", name, "uploaded_by"), "billing@supplier.test")
			self.assertTrue(any(f.endswith(".eml") for f in files_of(name)))
			self.assertTrue(frappe.db.exists("Comment", {"reference_name": name, "comment_type": "Comment"}))

	def test_email_without_pdf_gets_a_pdf_from_its_body(self):
		html = '<p>Danke für Ihren Einkauf: 12,99 €</p><img src="http://tracker.test/pixel.gif"><script>x()</script>'
		raw = email_bytes(subject="Your receipt from App Store", html=html)
		results = intake.create_receipts_from_file("receipt.eml", raw)
		doc = frappe.get_doc("Accounting Receipt", results[0]["receipt"])
		self.assertEqual(doc.title, "Your receipt from App Store")
		_, content = frappe.utils.file_manager.get_file(doc.attachment)
		self.assertTrue(content.startswith(b"%PDF"))

	def test_unsafe_tags_are_removed_before_rendering(self):
		cleaned = intake.UNSAFE_TAGS.sub("", '<p>ok</p><img src="http://x/y.png"><script>evil()</script><iframe src="x"></iframe>')
		self.assertEqual(cleaned, "<p>ok</p>")

	def test_other_files_are_refused(self):
		with self.assertRaises(intake.IntakeError):
			intake.create_receipts_from_file("photo.jpg", b"\xff\xd8\xff\xe0 not a receipt")

	def test_ai_never_fills_the_note(self):
		self.assertNotIn("note", [m["fieldname"] for m in get_extractable_fields_meta()])


class TestDatevStamp(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_note_lines_from_editor_html_and_back(self):
		self.assertEqual(
			note_to_lines('<div class="ql-editor"><p>Gäste: A &amp; B</p><p><br></p><p>Projekt P-1</p></div>'),
			["Gäste: A & B", "Projekt P-1"],
		)
		self.assertEqual(note_to_html("Gäste: A & B\n\nProjekt P-1"), "<p>Gäste: A &amp; B</p><p>Projekt P-1</p>")

	def test_short_note_becomes_a_band_and_keeps_pages_and_size(self):
		original = blank_pdf(pages=2, width=612, height=792)
		stamped, mode = stamp_pdf(original, "AR-TEST-1", ["Gäste: Anna, Ben", "Projekt PROJ-0042"])
		self.assertEqual(mode, "Band")
		reader = PdfReader(io.BytesIO(stamped))
		self.assertEqual(len(reader.pages), 2)
		self.assertAlmostEqual(float(reader.pages[0].mediabox.width), 612, places=0)
		self.assertAlmostEqual(float(reader.pages[0].mediabox.height), 792, places=0)
		self.assertIn("PROJ-0042", reader.pages[0].extract_text())

	def test_long_note_gets_a_cover_page(self):
		stamped, mode = stamp_pdf(blank_pdf(), "AR-TEST-2", [f"Gast {i}" for i in range(12)])
		self.assertEqual(mode, "Cover Page")
		reader = PdfReader(io.BytesIO(stamped))
		self.assertEqual(len(reader.pages), 2)
		self.assertIn("Gast 11", reader.pages[0].extract_text())
		self.assertIn("Hinweis für die Buchhaltung", reader.pages[0].extract_text())

	def test_send_to_datev_sends_the_stamped_copy(self):
		with patch.object(ar_module.frappe, "enqueue"):
			name = intake.create_receipts_from_file("bewirtung.pdf", blank_pdf())[0]["receipt"]
		frappe.db.set_value("Accounting Receipt", name, "note", "<p>Gäste: Anna Muster</p>")
		with patch.object(ar_module, "resolve_datev_recipient", return_value="up@datev.test"), \
			patch.object(ar_module.frappe, "sendmail") as sendmail:
			self.assertTrue(ar_module.send_to_datev(name)["ok"])
		attachment = sendmail.call_args.kwargs["attachments"][0]
		self.assertEqual(attachment["fname"], f"{name}-DATEV.pdf")
		self.assertIn("Anna Muster", PdfReader(io.BytesIO(attachment["fcontent"])).pages[0].extract_text())
		stamped_copies = [f for f in files_of(name) if f.startswith(f"{name}-DATEV")]
		self.assertEqual(len(stamped_copies), 1)
		with patch.object(ar_module, "resolve_datev_recipient", return_value="up@datev.test"), \
			patch.object(ar_module.frappe, "sendmail"):
			ar_module.preview_datev_pdf(name)  # a rebuild replaces the copy, it does not add one
		self.assertEqual(len([f for f in files_of(name) if f.startswith(f"{name}-DATEV")]), 1)

	def test_send_without_note_sends_the_original(self):
		with patch.object(ar_module.frappe, "enqueue"):
			name = intake.create_receipts_from_file("plain.pdf", blank_pdf())[0]["receipt"]
		with patch.object(ar_module, "resolve_datev_recipient", return_value="up@datev.test"), \
			patch.object(ar_module.frappe, "sendmail") as sendmail:
			ar_module.send_to_datev(name)
		self.assertIn("file_url", sendmail.call_args.kwargs["attachments"][0])
