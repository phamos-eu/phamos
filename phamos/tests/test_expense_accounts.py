# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Expense accounts offered to the AI and Purchase Invoices built from receipt lines."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, expense_accounts
from phamos.api import accounting_receipts as api

SUPPLIER = "Account Test Lieferant GmbH"


def skr04_company():
	for company in frappe.get_all("Company", pluck="name"):
		if expense_accounts.chart_family(company) == "SKR04":
			return company
	return None


class AccountTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = skr04_company()
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		expense_accounts.ensure_account_fields()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		expense_accounts.clear_account_cache()

	def account(self, number):
		return expense_accounts.account_by_number(self.company, number)

	def receipt(self, lines, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Account test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": "RE-ACC-1",
				"posting_date": "2026-10-01",
				"items": lines,
				**values,
			}
		)
		return doc.insert(ignore_permissions=True)


class TestExpenseAccounts(AccountTestCase):
	def test_seed_marks_skr04_accounts_with_keywords_and_keeps_edits(self):
		telekom = self.account("6805")
		frappe.db.set_value("Account", telekom, expense_accounts.KEYWORDS_FIELD, "meine eigenen wörter")
		result = expense_accounts.seed_expense_accounts(self.company)
		self.assertIn(telekom, result["marked"])
		self.assertEqual(frappe.db.get_value("Account", telekom, expense_accounts.SELECTABLE_FIELD), 1)
		self.assertEqual(frappe.db.get_value("Account", telekom, expense_accounts.KEYWORDS_FIELD), "meine eigenen wörter")
		self.assertIn("restaurant", frappe.db.get_value("Account", self.account("6640"), expense_accounts.KEYWORDS_FIELD))

	def test_ai_list_holds_only_marked_expense_accounts(self):
		expense_accounts.seed_expense_accounts(self.company)
		frappe.db.set_value("Account", self.account("6610"), expense_accounts.SELECTABLE_FIELD, 0)
		expense_accounts.clear_account_cache()
		by_number = {a["account_number"]: a for a in expense_accounts.ai_expense_accounts(self.company)}
		self.assertIn("6805", by_number)
		self.assertNotIn("6610", by_number)
		self.assertIn("magentamobil", by_number["6805"]["keywords"])

	def test_setup_does_not_reseed_a_company_with_chosen_accounts(self):
		expense_accounts.seed_expense_accounts(self.company)
		frappe.db.set_value("Account", self.account("6610"), expense_accounts.SELECTABLE_FIELD, 0)
		expense_accounts.ensure_expense_account_setup()
		self.assertEqual(frappe.db.get_value("Account", self.account("6610"), expense_accounts.SELECTABLE_FIELD), 0)

	def test_tax_template_by_rate(self):
		self.assertTrue(expense_accounts.item_tax_template_for_rate(19, self.company))
		self.assertIsNone(expense_accounts.item_tax_template_for_rate(None, self.company))

	def test_line_account_is_saved_through_the_cockpit_api(self):
		doc = self.receipt([{"item_name": "Domain phamos.eu", "qty": 1, "rate": 12, "amount": 12}])
		row = doc.items[0]
		api.update_receipt(doc.name, items=[{"name": row.name, "item_name": row.item_name, "qty": 1, "rate": 12,
			"expense_account": self.account("6810")}])
		self.assertEqual(frappe.db.get_value("Accounting Receipt Item", row.name, "expense_account"), self.account("6810"))


class TestPurchaseInvoiceFromLines(AccountTestCase):
	def test_invoice_lines_accounts_tax_template_and_header(self):
		doc = self.receipt(
			[
				{"item_name": "MagentaMobil M Business", "qty": 2, "rate": 39.95, "amount": 79.9, "tax_rate": 19, "expense_account": self.account("6805")},
				{"item_name": "Fachbuch ERPNext", "qty": 1, "rate": 30, "amount": 30, "tax_rate": 7, "expense_account": self.account("6820")},
			],
			due_date="2026-10-15",
		)
		pi = branching.make_purchase_invoice(doc)
		self.assertEqual(pi.supplier, SUPPLIER)
		self.assertEqual(pi.bill_no, "RE-ACC-1")
		self.assertEqual(str(pi.posting_date), "2026-10-01")
		self.assertEqual([(r.item_code, r.item_name, r.qty, r.rate) for r in pi.items],
			[(None, "MagentaMobil M Business", 2, 39.95), (None, "Fachbuch ERPNext", 1, 30)])
		self.assertEqual([r.expense_account for r in pi.items], [self.account("6805"), self.account("6820")])
		self.assertTrue(pi.items[0].item_tax_template)
		self.assertNotEqual(pi.items[0].item_tax_template, pi.items[1].item_tax_template)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "purchase_invoice"), pi.name)
		self.assertEqual(pi.docstatus, 0)

	def test_line_without_account_is_refused(self):
		doc = self.receipt([{"item_name": "Mystery line", "qty": 1, "rate": 10, "amount": 10}])
		with self.assertRaises(branching.LineWithoutAccount):
			branching.make_purchase_invoice(doc)

	def test_any_expense_account_works_not_only_the_ai_ones(self):
		doc = self.receipt([{"item_name": "Sonderposten", "qty": 1, "rate": 10, "amount": 10, "expense_account": self.account("6450")}])
		pi = branching.make_purchase_invoice(doc)
		self.assertEqual(pi.items[0].expense_account, self.account("6450"))

	def test_total_difference_is_reported_and_second_invoice_refused(self):
		doc = self.receipt([{"item_name": "Server", "qty": 1, "rate": 100, "amount": 100, "expense_account": self.account("6810")}], sum=500)
		pi = branching.make_purchase_invoice(doc)
		self.assertTrue(pi.flags.receipt_warnings)
		doc.reload()
		with self.assertRaises(frappe.ValidationError):
			branching.make_purchase_invoice(doc)

	def test_supplier_and_lines_are_required(self):
		with self.assertRaises(frappe.ValidationError):
			branching.make_purchase_invoice(self.receipt([], supplier=None))
		with self.assertRaises(frappe.ValidationError):
			branching.make_purchase_invoice(self.receipt([]))
