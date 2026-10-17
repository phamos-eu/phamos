# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Approving a receipt to pay needs a submitted Purchase Invoice."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, expense_accounts
from phamos.api import accounting_receipts, accounting_spa

SUPPLIER = "Approval Test Lieferant GmbH"


class TestApproveNeedsSubmittedInvoice(FrappeTestCase):
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
