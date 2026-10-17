# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Booking receipts as Expense Claim or Journal Entry, and the net/VAT split behind both."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, expense_accounts
from phamos.api import accounting_receipts

SUPPLIER = "Booking Test Lieferant GmbH"


class BookingTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = next((c for c in frappe.get_all("Company", pluck="name") if expense_accounts.chart_family(c) == "SKR04"), None)
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)
		self.currency = frappe.db.get_value("Company", self.company, "default_currency")

	def tearDown(self):
		frappe.db.rollback()

	def account(self, number):
		return expense_accounts.account_by_number(self.company, number)

	def receipt(self, lines, **values):
		return frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Booking test",
				"company": self.company,
				"currency": self.currency,
				"conversion_rate": 1,
				"supplier_reference": "BT-1",
				"posting_date": "2026-10-01",
				"items": lines,
				**values,
			}
		).insert(ignore_permissions=True)

	def employee(self):
		gender = frappe.db.get_value("Gender", {}, "name")
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "Booking",
				"last_name": "Tester",
				"gender": gender,
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": self.company,
				"status": "Active",
			}
		).insert(ignore_permissions=True).name


class TestNetAndVat(BookingTestCase):
	def test_input_vat_accounts_by_rate(self):
		self.assertEqual(frappe.db.get_value("Account", branching.input_vat_account(19, self.company), "account_number"), "1406")
		self.assertEqual(frappe.db.get_value("Account", branching.input_vat_account(7, self.company), "account_number"), "1401")
		self.assertIsNone(branching.input_vat_account(0, self.company))

	def test_gross_lines_are_split(self):
		doc = self.receipt([{"item_name": "Essen", "qty": 1, "rate": 119, "amount": 119, "tax_rate": 19, "expense_account": self.account("6640")}], sum=119)
		split = branching.net_lines_and_taxes(doc, self.company)
		self.assertTrue(split["lines_are_gross"])
		self.assertEqual((split["lines"][0]["net"], split["taxes"][0]["amount"], split["total"]), (100, 19, 119))

	def test_net_lines_with_mixed_rates_and_rounding(self):
		doc = self.receipt(
			[
				{"item_name": "Buch", "qty": 1, "rate": 10, "amount": 10, "tax_rate": 7, "expense_account": self.account("6820")},
				{"item_name": "Toner", "qty": 1, "rate": 33.33, "amount": 33.33, "tax_rate": 19, "expense_account": self.account("6815")},
			],
			net_total=43.33, total_taxes=7.03, sum=50.36,
		)
		split = branching.net_lines_and_taxes(doc, self.company)
		self.assertFalse(split["lines_are_gross"])
		self.assertEqual([t["rate"] for t in split["taxes"]], [7, 19])
		self.assertEqual(split["total"], 50.36)

	def test_lines_need_accounts(self):
		doc = self.receipt([{"item_name": "Ohne Konto", "qty": 1, "rate": 5, "amount": 5}])
		with self.assertRaises(branching.LineWithoutAccount):
			branching.net_lines_and_taxes(doc, self.company)


class TestExpenseClaim(BookingTestCase):
	def test_draft_claim_reimburses_the_employee_net_plus_vat(self):
		employee = self.employee()
		doc = self.receipt([{"item_name": "Bahnticket", "qty": 1, "rate": 119, "amount": 119, "tax_rate": 19,
			"expense_account": self.account("6663")}], sum=119)
		result = accounting_receipts.make_expense_claim(doc.name, employee=employee)
		claim = frappe.get_doc("Expense Claim", result["expense_claim"])
		self.assertEqual((claim.docstatus, claim.employee), (0, employee))
		self.assertEqual([(e.default_account, e.sanctioned_amount) for e in claim.expenses], [(self.account("6663"), 100)])
		self.assertEqual([(t.account_head, t.tax_amount) for t in claim.taxes], [(branching.input_vat_account(19, self.company), 19)])
		self.assertEqual(claim.grand_total, 119)
		self.assertEqual(result["receipt"]["expense_claim"], claim.name)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "employee"), employee)

	def test_one_booking_per_receipt(self):
		employee = self.employee()
		doc = self.receipt([{"item_name": "Taxi", "qty": 1, "rate": 20, "amount": 20, "expense_account": self.account("6663")}],
			supplier=SUPPLIER, sum=20)
		accounting_receipts.make_expense_claim(doc.name, employee=employee)
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.make_journal_entry(doc.name, credit_account=self.bank())
		with self.assertRaises(frappe.ValidationError):
			branching.make_purchase_invoice(frappe.get_doc("Accounting Receipt", doc.name))

	def test_employee_is_required(self):
		doc = self.receipt([{"item_name": "Taxi", "qty": 1, "rate": 20, "amount": 20, "expense_account": self.account("6663")}], sum=20)
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.make_expense_claim(doc.name)

	def bank(self):
		return frappe.db.get_value("Account", {"company": self.company, "account_type": "Bank", "is_group": 0}, "name")


class TestJournalEntry(BookingTestCase):
	def bank(self):
		return frappe.db.get_value("Account", {"company": self.company, "account_type": "Bank", "is_group": 0}, "name")

	def test_draft_entry_balances_and_submits(self):
		doc = self.receipt(
			[
				{"item_name": "Kontoführung", "qty": 1, "rate": 12, "amount": 12, "tax_rate": 0, "expense_account": self.account("6855")},
				{"item_name": "Kartenentgelt", "qty": 1, "rate": 23.8, "amount": 23.8, "tax_rate": 19, "expense_account": self.account("6855")},
			],
			sum=35.8,
		)
		result = accounting_receipts.make_journal_entry(doc.name, credit_account=self.bank())
		je = frappe.get_doc("Journal Entry", result["journal_entry"])
		self.assertEqual((je.voucher_type, je.docstatus, je.cheque_no), ("Bank Entry", 0, "BT-1"))
		self.assertEqual(je.total_debit, je.total_credit)
		self.assertEqual(je.total_credit, 35.8)
		debits = sorted((a.account, a.debit_in_account_currency) for a in je.accounts if a.debit_in_account_currency)
		self.assertIn((branching.input_vat_account(19, self.company), 3.8), debits)
		je.submit()
		self.assertEqual(result["receipt"]["journal_entry"], je.name)

	def test_payable_credit_and_foreign_currency_are_refused(self):
		doc = self.receipt([{"item_name": "Gebühr", "qty": 1, "rate": 5, "amount": 5, "expense_account": self.account("6855")}], sum=5)
		payable = frappe.db.get_value("Account", {"company": self.company, "account_type": "Payable", "is_group": 0}, "name")
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.make_journal_entry(doc.name, credit_account=payable)
		doc.db_set("currency", "USD")
		with self.assertRaises(frappe.ValidationError):
			accounting_receipts.make_journal_entry(doc.name, credit_account=self.bank())

	def test_booking_options_preview(self):
		doc = self.receipt([{"item_name": "Gebühr", "qty": 1, "rate": 11.9, "amount": 11.9, "tax_rate": 19,
			"expense_account": self.account("6855")}], sum=11.9)
		options = accounting_receipts.get_booking_options(doc.name)
		self.assertEqual(options["split"]["total"], 11.9)
		self.assertTrue(options["credit_accounts"])
