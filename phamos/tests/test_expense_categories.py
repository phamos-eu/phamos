# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Expense categories and Purchase Invoices built from receipt lines."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, categories
from phamos.api import accounting_receipts as api

SUPPLIER = "Category Test Lieferant GmbH"


def skr04_company():
	for company in frappe.get_all("Company", pluck="name"):
		if categories.chart_family(company) == "SKR04":
			return company
	return None


class CategoryTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = skr04_company()
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		categories.ensure_keywords_field()
		categories.seed_expense_categories(self.company)
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		categories.clear_category_cache()

	def account(self, number):
		return categories.account_by_number(self.company, number)

	def receipt(self, lines, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Category test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": "RE-CAT-1",
				"posting_date": "2026-10-01",
				"items": lines,
				**values,
			}
		)
		return doc.insert(ignore_permissions=True)


class TestCategories(CategoryTestCase):
	def test_seed_creates_categories_with_skr04_accounts_and_is_idempotent(self):
		self.assertEqual(categories.resolve_expense_account("Telekommunikation", self.company), self.account("6805"))
		self.assertEqual(categories.resolve_expense_account("Software-Abos", self.company), self.account("6837"))
		self.assertIn("magentamobil", frappe.db.get_value("Item", "Telekommunikation", categories.KEYWORDS_FIELD))
		again = categories.seed_expense_categories(self.company)
		self.assertFalse(again["created"])
		self.assertIn("Telekommunikation", again["skipped"])

	def test_category_list_for_the_picker(self):
		by_code = {c["item_code"]: c for c in categories.expense_categories(self.company)}
		self.assertEqual(by_code["Bewirtung"]["account_number"], "6640")
		self.assertIn("restaurant", by_code["Bewirtung"]["keywords"])

	def test_new_category_needs_an_expense_account_of_the_company(self):
		name = categories.create_expense_category("Internet-Anschluss Test", self.account("6810"), self.company, "dsl, glasfaser")
		self.assertEqual(categories.resolve_expense_account(name, self.company), self.account("6810"))
		income = frappe.db.get_value("Account", {"company": self.company, "root_type": "Income", "is_group": 0}, "name")
		with self.assertRaises(frappe.ValidationError):
			categories.create_expense_category("Wrong account", income, self.company)
		with self.assertRaises(frappe.ValidationError):
			categories.create_expense_category("Telekommunikation", self.account("6805"), self.company)

	def test_tax_template_by_rate(self):
		self.assertTrue(categories.item_tax_template_for_rate(19, self.company))
		self.assertIsNone(categories.item_tax_template_for_rate(None, self.company))

	def test_lines_take_the_category_account_and_follow_category_changes(self):
		doc = self.receipt([{"item_name": "MagentaMobil M", "qty": 1, "rate": 40, "amount": 40, "item_code": "Telekommunikation"}])
		self.assertEqual(doc.items[0].expense_account, self.account("6805"))
		row = doc.items[0]
		api.update_receipt(doc.name, items=[{"name": row.name, "item_name": row.item_name, "qty": 1, "rate": 40,
			"item_code": "Hosting & Cloud", "expense_account": row.expense_account}])
		self.assertEqual(frappe.db.get_value("Accounting Receipt Item", row.name, "expense_account"), self.account("6810"))


	def test_chosen_account_brings_its_category(self):
		doc = self.receipt([{"item_name": "Domain phamos.eu", "qty": 1, "rate": 12, "amount": 12, "expense_account": self.account("6810")}])
		self.assertEqual(doc.items[0].item_code, "Hosting & Cloud")
		self.assertEqual(categories.category_for_account(self.account("6810"), self.company), "Hosting & Cloud")

	def test_account_without_single_category_leaves_the_category_empty(self):
		doc = self.receipt([{"item_name": "Sonderposten", "qty": 1, "rate": 5, "amount": 5, "expense_account": self.account("6450")}])
		self.assertFalse(doc.items[0].item_code)
		self.assertEqual(doc.items[0].expense_account, self.account("6450"))

	def test_changing_the_account_replaces_a_mismatching_category(self):
		doc = self.receipt([{"item_name": "Handy", "qty": 1, "rate": 40, "amount": 40, "item_code": "Telekommunikation"}])
		row = doc.items[0]
		api.update_receipt(doc.name, items=[{"name": row.name, "item_name": "Handy", "qty": 1, "rate": 40,
			"item_code": None, "expense_account": self.account("6815")}])
		self.assertEqual(frappe.db.get_value("Accounting Receipt Item", row.name, "item_code"), "Bürobedarf")


class TestPurchaseInvoiceFromLines(CategoryTestCase):
	def test_invoice_lines_accounts_tax_template_and_header(self):
		doc = self.receipt(
			[
				{"item_name": "MagentaMobil M Business", "qty": 2, "rate": 39.95, "amount": 79.9, "tax_rate": 19, "item_code": "Telekommunikation"},
				{"item_name": "Fachbuch ERPNext", "qty": 1, "rate": 30, "amount": 30, "tax_rate": 7, "item_code": "Fachliteratur"},
			],
			due_date="2026-10-15",
		)
		pi = branching.make_purchase_invoice(doc)
		self.assertEqual(pi.supplier, SUPPLIER)
		self.assertEqual(pi.bill_no, "RE-CAT-1")
		self.assertEqual(str(pi.posting_date), "2026-10-01")
		self.assertEqual([(r.item_code, r.item_name, r.qty, r.rate) for r in pi.items],
			[("Telekommunikation", "MagentaMobil M Business", 2, 39.95), ("Fachliteratur", "Fachbuch ERPNext", 1, 30)])
		self.assertEqual([r.expense_account for r in pi.items], [self.account("6805"), self.account("6820")])
		self.assertTrue(pi.items[0].item_tax_template)
		self.assertNotEqual(pi.items[0].item_tax_template, pi.items[1].item_tax_template)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "purchase_invoice"), pi.name)
		self.assertEqual(pi.docstatus, 0)

	def test_line_without_category_or_account_is_refused(self):
		doc = self.receipt([{"item_name": "Mystery line", "qty": 1, "rate": 10, "amount": 10}])
		with self.assertRaises(branching.LineWithoutAccount):
			branching.make_purchase_invoice(doc)

	def test_line_with_own_account_needs_no_category(self):
		doc = self.receipt([{"item_name": "Sonderposten", "qty": 1, "rate": 10, "amount": 10, "expense_account": self.account("6450")}])
		pi = branching.make_purchase_invoice(doc)
		self.assertFalse(pi.items[0].item_code)
		self.assertEqual(pi.items[0].expense_account, self.account("6450"))

	def test_total_difference_is_reported_and_second_invoice_refused(self):
		doc = self.receipt([{"item_name": "Server", "qty": 1, "rate": 100, "amount": 100, "item_code": "Hosting & Cloud"}], sum=500)
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
