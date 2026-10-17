# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Approving a receipt to pay needs a submitted Purchase Invoice."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, expense_accounts
from phamos.api import accounting_receipts, accounting_spa

SUPPLIER = "Approval Test Lieferant GmbH"


class ApprovalTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = next(
			(c for c in frappe.get_all("Company", pluck="name") if expense_accounts.chart_family(c) == "SKR04"), None
		)
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def receipt(self):
		return frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Approval test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": "RE-APP-1",
				"posting_date": "2026-10-01",
				"sum": 10,
				"items": [{"item_name": "Toner", "qty": 1, "rate": 10, "amount": 10,
					"expense_account": expense_accounts.account_by_number(self.company, "6815")}],
			}
		).insert(ignore_permissions=True)

class TestApproveNeedsSubmittedInvoice(ApprovalTestCase):
	def test_without_invoice_approval_is_refused(self):
		doc = self.receipt()
		with self.assertRaises(frappe.ValidationError):
			accounting_spa.update_receipt_status(doc.name, "Approved to Pay")
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "status"), "Inbox")

	def test_draft_invoice_is_not_enough_and_submitting_it_unlocks_approval(self):
		doc = self.receipt()
		branching.make_purchase_invoice(doc)
		row = accounting_spa.get_receipt(doc.name)
		self.assertEqual(row["purchase_invoice_docstatus"], 0)
		with self.assertRaises(frappe.ValidationError):
			accounting_spa.update_receipt_status(doc.name, "Approved to Pay")
		result = accounting_receipts.submit_purchase_invoice(doc.name)
		self.assertEqual(result["receipt"]["purchase_invoice_docstatus"], 1)
		self.assertEqual(accounting_spa.update_receipt_status(doc.name, "Approved to Pay")["status"], "Approved to Pay")

	def test_cancelled_invoice_does_not_count(self):
		doc = self.receipt()
		pi = branching.make_purchase_invoice(doc)
		pi.submit()
		pi.cancel()
		with self.assertRaises(frappe.ValidationError):
			accounting_spa.update_receipt_status(doc.name, "Approved to Pay")

	def test_receipts_approved_earlier_can_still_be_edited(self):
		doc = self.receipt()
		frappe.db.set_value("Accounting Receipt", doc.name, "status", "Approved to Pay")
		doc = frappe.get_doc("Accounting Receipt", doc.name)
		doc.title = "Edited later"
		doc.save()
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "title"), "Edited later")

	def test_submitting_needs_a_draft(self):
		doc = self.receipt()
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.submit_purchase_invoice(doc.name)


class TestApproveCreatesPaymentRequest(ApprovalTestCase):
	def setUp(self):
		super().setUp()
		if not frappe.db.exists("Bank", "Approval Test Bank"):
			frappe.get_doc({"doctype": "Bank", "bank_name": "Approval Test Bank"}).insert(ignore_permissions=True)
		used = frappe.get_all("Bank Account", filters={"account": ("is", "set")}, pluck="account")
		gl = frappe.db.get_value("Account", {"company": self.company, "account_type": "Bank", "is_group": 0,
			"name": ("not in", used or [""])}, "name")
		if not gl:
			raise unittest.SkipTest("needs a bank ledger account that no Bank Account uses yet")
		self.bank_account = frappe.get_doc(
			{
				"doctype": "Bank Account",
				"account_name": "Approval Test Konto",
				"bank": "Approval Test Bank",
				"is_company_account": 1,
				"company": self.company,
				"account": gl,
				"iban": "DE89370400440532013000",
			}
		).insert(ignore_permissions=True)

	def approved_receipt_with_invoice(self):
		doc = self.receipt()
		branching.make_purchase_invoice(doc).submit()
		return doc

	def test_approve_creates_a_submitted_outward_payment_request(self):
		doc = self.approved_receipt_with_invoice()
		options = accounting_receipts.get_approval_options(doc.name)
		self.assertIn(self.bank_account.name, [a.name for a in options["bank_accounts"]])
		result = accounting_receipts.approve_receipt(doc.name, bank_account=self.bank_account.name, mode_of_payment="Wire Transfer",
			due_date="2026-10-20")
		pr = frappe.get_doc("Payment Request", result["payment_request"])
		self.assertEqual((pr.docstatus, pr.payment_request_type, pr.status), (1, "Outward", "Initiated"))
		self.assertEqual((pr.reference_doctype, pr.party), ("Purchase Invoice", SUPPLIER))
		self.assertEqual(pr.grand_total, 10)
		self.assertIn("Approval Test Konto", pr.message)
		self.assertIn("RE-APP-1", pr.subject)
		receipt = result["receipt"]
		self.assertEqual((receipt["status"], receipt["payment_request"], receipt["bank_account"]), ("Approved to Pay", pr.name, self.bank_account.name))
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "payment_account"), self.bank_account.account)
		again = accounting_receipts.approve_receipt(doc.name, create_payment_request=1)
		self.assertEqual(again["payment_request"], pr.name)
		self.assertEqual(frappe.db.count("Payment Request", {"reference_name": pr.reference_name, "docstatus": 1}), 1)

	def test_dont_pay_cancels_the_open_payment_request(self):
		doc = self.approved_receipt_with_invoice()
		pr = accounting_receipts.approve_receipt(doc.name, bank_account=self.bank_account.name)["payment_request"]
		accounting_spa.update_receipt_status(doc.name, "Do Not Pay")
		self.assertEqual(frappe.db.get_value("Payment Request", pr, ["docstatus", "status"]), (2, "Cancelled"))

	def test_approval_without_invoice_creates_nothing(self):
		doc = self.receipt()
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.approve_receipt(doc.name, bank_account=self.bank_account.name)
		self.assertFalse(frappe.db.get_value("Accounting Receipt", doc.name, "payment_request"))

	def test_paying_from_another_companys_account_is_refused(self):
		doc = self.approved_receipt_with_invoice()
		self.bank_account.db_set("is_company_account", 0)
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.approve_receipt(doc.name, bank_account=self.bank_account.name)
