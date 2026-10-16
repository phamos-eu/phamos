# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting Receipt inbox foundation: status, permissions, DATEV routing, setup."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import accounting_spa
from phamos.patches.v1_0.convert_accounting_receipt_status import convert_status
from phamos.phamos.doctype.accounting_receipt import accounting_receipt as ar_module
from phamos.setup.accounting_receipt import AI_ACCOUNTANT_ROLE, ensure_accounting_receipt_setup

STATUS_OPTIONS = [
	"Inbox",
	"Needs Decision",
	"Approved to Pay",
	"Do Not Pay",
	"Sent to DATEV",
	"Paid",
	"Cancelled",
]


def _make_receipt(**values):
	doc = frappe.get_doc(
		{
			"doctype": "Accounting Receipt",
			"title": values.pop("title", "Test receipt"),
			"currency": "EUR",
			"conversion_rate": 1,
			**values,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestConvertStatus(FrappeTestCase):
	def test_valid_status_is_kept(self):
		self.assertEqual(convert_status({"status": "Do Not Pay"}, STATUS_OPTIONS), "Do Not Pay")

	def test_blank_status_is_derived_from_flags(self):
		self.assertEqual(convert_status({"status": "", "is_paid": 1, "sent_to_datev": 1}, STATUS_OPTIONS), "Paid")
		self.assertEqual(convert_status({"status": None, "sent_to_datev": 1}, STATUS_OPTIONS), "Sent to DATEV")
		self.assertEqual(convert_status({"status": " "}, STATUS_OPTIONS), "Inbox")

	def test_unknown_text_needs_a_human(self):
		self.assertEqual(convert_status({"status": "Open"}, STATUS_OPTIONS), "Needs Decision")


class TestDatevRecipient(FrappeTestCase):
	ROWS = [
		frappe._dict(email="invoices@datev.test", receipt_types="Purchase Invoice, Payment", is_default=1),
		frappe._dict(email="other@datev.test", receipt_types="Sonstiges", is_default=0),
	]

	def _resolve(self, receipt_type, rows):
		doc = frappe._dict(receipt_type=receipt_type, datev_mail_recipient="legacy-1@datev.test",
			datev_mail_recipient_2="legacy-2@datev.test")
		with patch.object(ar_module.frappe, "get_all", return_value=rows):
			return ar_module.resolve_datev_recipient(doc)

	def test_type_match_wins(self):
		self.assertEqual(self._resolve("Sonstiges", self.ROWS), "other@datev.test")
		self.assertEqual(self._resolve("purchase invoice", self.ROWS), "invoices@datev.test")

	def test_default_row_for_unlisted_or_empty_type(self):
		self.assertEqual(self._resolve("Journal Entry", self.ROWS), "invoices@datev.test")
		self.assertEqual(self._resolve("", self.ROWS), "invoices@datev.test")

	def test_no_default_row_means_no_recipient(self):
		self.assertIsNone(self._resolve("Journal Entry", [self.ROWS[1]]))

	def test_empty_table_falls_back_to_legacy_fields(self):
		self.assertEqual(self._resolve("Sonstiges", []), "legacy-2@datev.test")
		self.assertEqual(self._resolve("Purchase Invoice", []), "legacy-1@datev.test")


class TestAccountingReceiptInbox(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_new_receipt_starts_in_inbox_and_titles_may_repeat(self):
		first = _make_receipt(title="Telekom Rechnung")
		second = _make_receipt(title="Telekom Rechnung")
		self.assertEqual(first.status, "Inbox")
		self.assertNotEqual(first.name, second.name)

	def test_cancel_reason_is_cleared_outside_cancelled(self):
		doc = _make_receipt(status="Needs Decision", cancel_reason="Duplicate")
		self.assertIsNone(doc.cancel_reason)

	def test_sync_never_replaces_a_chosen_attachment(self):
		doc = _make_receipt(attachment="/private/files/chosen.pdf")
		with patch.object(ar_module, "_first_attached_pdf", return_value="/private/files/other.pdf") as first, \
			patch("phamos.ai_agents.runner.enqueue_run") as enqueue:
			ar_module._sync_attachment_field(doc.name)
		first.assert_not_called()
		enqueue.assert_not_called()
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "attachment"), "/private/files/chosen.pdf")

	def test_sync_fills_an_empty_attachment_and_queues_extraction(self):
		doc = _make_receipt()
		with patch.object(ar_module, "_first_attached_pdf", return_value="/private/files/first.pdf"), \
			patch("phamos.ai_agents.runner.enqueue_run") as enqueue:
			ar_module._sync_attachment_field(doc.name)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "attachment"), "/private/files/first.pdf")
		enqueue.assert_called_once()

	def test_send_to_datev_requires_write_permission(self):
		doc = _make_receipt(attachment="/private/files/r.pdf")
		with patch.object(ar_module.frappe, "has_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				ar_module.send_to_datev(doc.name)

	def test_send_to_datev_moves_status_and_records_audit(self):
		doc = _make_receipt(attachment="/private/files/r.pdf", status="Needs Decision")
		with patch.object(ar_module, "resolve_datev_recipient", return_value="up@datev.test"), \
			patch.object(ar_module.frappe, "sendmail") as sendmail:
			result = ar_module.send_to_datev(doc.name)
		self.assertTrue(result["ok"], result)
		sendmail.assert_called_once()
		self.assertEqual(sendmail.call_args.kwargs["recipients"], ["up@datev.test"])
		values = frappe.db.get_value("Accounting Receipt", doc.name, ["status", "sent_to_datev", "datev_sent_by"], as_dict=True)
		self.assertEqual(values.status, "Sent to DATEV")
		self.assertEqual(values.sent_to_datev, 1)
		self.assertEqual(values.datev_sent_by, "Administrator")

	def test_send_to_datev_keeps_paid_status_and_refuses_cancelled(self):
		paid = _make_receipt(attachment="/private/files/p.pdf", status="Paid", is_paid=1)
		cancelled = _make_receipt(attachment="/private/files/c.pdf", status="Cancelled", cancel_reason="Duplicate")
		with patch.object(ar_module, "resolve_datev_recipient", return_value="up@datev.test"), \
			patch.object(ar_module.frappe, "sendmail") as sendmail:
			self.assertTrue(ar_module.send_to_datev(paid.name)["ok"])
			self.assertFalse(ar_module.send_to_datev(cancelled.name)["ok"])
		self.assertEqual(sendmail.call_count, 1)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", paid.name, "status"), "Paid")

	def test_board_refuses_a_fake_datev_send(self):
		doc = _make_receipt()
		with self.assertRaises(frappe.ValidationError):
			accounting_spa.update_receipt_status(doc.name, "Sent to DATEV")
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "sent_to_datev"), 0)

	def test_board_drop_on_paid_records_the_payment(self):
		doc = _make_receipt()
		row = accounting_spa.update_receipt_status(doc.name, "Paid")
		self.assertEqual(row["status"], "Paid")
		self.assertEqual(row["is_paid"], 1)
		self.assertEqual(str(frappe.db.get_value("Accounting Receipt", doc.name, "payment_date")), frappe.utils.today())

	def test_receipt_list_hides_cancelled_and_knows_the_pdf(self):
		with_pdf = _make_receipt(attachment="/private/files/a.pdf")
		cancelled = _make_receipt(status="Cancelled", cancel_reason="Other")
		rows = {row["name"]: row for row in accounting_spa.get_receipts()}
		self.assertTrue(rows[with_pdf.name]["has_pdf"])
		self.assertNotIn(cancelled.name, rows)


class TestAccountingReceiptSetup(FrappeTestCase):
	def test_setup_is_idempotent(self):
		ensure_accounting_receipt_setup()
		ensure_accounting_receipt_setup()
		user = frappe.db.get_single_value("phamos Settings", "ai_accountant_user")
		self.assertTrue(frappe.db.exists("User", user))
		self.assertIn(AI_ACCOUNTANT_ROLE, frappe.get_roles(user))
		self.assertTrue(frappe.get_meta("Issue").has_field("accounting_receipt"))
		if "raven" in frappe.get_installed_apps():
			self.assertTrue(frappe.db.exists("Raven Bot", "AI Accountant"))
