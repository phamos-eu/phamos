# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Per-supplier AI settings and how the decision and the account proposal use them."""

import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import classify, decide, expense_accounts, library, supplier_settings
from phamos.ai_agents import llm

SUPPLIER = "Settings Test Telco GmbH"


class TestSupplierSettings(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		supplier_settings.ensure_fields()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)
		self.company = next((c for c in frappe.get_all("Company", pluck="name") if expense_accounts.chart_family(c) == "SKR04"), None)
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		frappe.db.delete("Account Assignment", {"supplier": SUPPLIER})

	def tearDown(self):
		frappe.db.rollback()

	def account(self, number):
		return expense_accounts.account_by_number(self.company, number)

	def configure(self, **values):
		supplier_settings.save_settings(SUPPLIER, values)

	def receipt(self, status=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Settings test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": values.pop("supplier_reference", frappe.generate_hash(length=8)),
				"posting_date": values.pop("posting_date", "2026-10-01"),
				"sum": 40,
				"receipt_type": "Invoice",
				"items": values.pop("items", [{"item_name": "Mobilfunk", "qty": 1, "rate": 40, "amount": 40, "expense_account": self.account("6805")}]),
				**values,
			}
		).insert(ignore_permissions=True)
		if status:
			doc.db_set("status", status)
		return doc

	def history(self):
		for month, amount in ((1, 40), (2, 41), (3, 39)):
			self.receipt(status="Sent to DATEV", sum=amount, posting_date=f"2026-0{month}-10")

	def test_defaults_are_empty(self):
		self.assertEqual(supplier_settings.get(SUPPLIER), {})

	def test_always_review(self):
		self.history()
		self.assertEqual(decide.evaluate(self.receipt())["decision"], "approve_to_pay")
		self.configure(always_review=1)
		result = decide.evaluate(self.receipt())
		self.assertEqual(result["decision"], "needs_human")
		self.assertIn("supplier_review", [f["code"] for f in result["flags"]])

	def test_tolerance_override(self):
		self.history()
		self.assertIn("unusual_amount", [f["code"] for f in decide.evaluate(self.receipt(sum=80))["flags"]])
		self.configure(amount_tolerance_pct=150)
		self.assertNotIn("unusual_amount", [f["code"] for f in decide.evaluate(self.receipt(sum=80))["flags"]])

	def test_direct_debit_counts_as_paid(self):
		self.history()
		self.configure(payment_mode="Direct Debit")
		result = decide.evaluate(self.receipt())
		self.assertEqual((result["decision"], result["paid"]), ("auto_datev", True))

	def test_auto_datev_follows_the_supplier_choice(self):
		self.history()
		self.configure(payment_mode="Direct Debit", auto_datev="Allow")
		doc = self.receipt()
		with patch("phamos.phamos.doctype.accounting_receipt.accounting_receipt.send_to_datev") as send:
			decide.apply_decision(doc, decide.evaluate(doc), decide.DEFAULT_PARAMS)
		send.assert_called_once_with(doc.name)
		self.configure(auto_datev="Never")
		doc = self.receipt()
		with patch("phamos.phamos.doctype.accounting_receipt.accounting_receipt.send_to_datev") as send:
			decide.apply_decision(doc, decide.evaluate(doc), {**decide.DEFAULT_PARAMS, "auto_datev": 1})
		send.assert_not_called()

	def test_default_account_and_cost_center_before_mistral(self):
		cost_center = frappe.db.get_value("Cost Center", {"company": self.company, "is_group": 0}, "name")
		self.configure(expense_account=self.account("6805"), cost_center=cost_center)
		doc = self.receipt(items=[{"item_name": "Roaming Paket EU", "qty": 1, "rate": 40, "amount": 40}])
		with patch.object(llm, "chat_json") as chat:
			result = classify.classify_receipt(frappe.get_doc("Accounting Receipt", doc.name), dict(classify.DEFAULT_PARAMS))
		chat.assert_not_called()
		doc.reload()
		self.assertEqual((doc.items[0].expense_account, doc.items[0].assignment_source), (self.account("6805"), "Supplier Default"))
		self.assertEqual(doc.cost_center, cost_center)
		self.assertEqual(result["unclear"], 0)

	def test_confirmed_library_entry_beats_the_default(self):
		self.configure(expense_account=self.account("6805"))
		library.learn(self.company, SUPPLIER, "Router Miete", self.account("6810"))
		doc = self.receipt(items=[{"item_name": "Router Miete", "qty": 1, "rate": 40, "amount": 40}])
		classify.classify_receipt(frappe.get_doc("Accounting Receipt", doc.name), dict(classify.DEFAULT_PARAMS, use_llm=0))
		doc.reload()
		self.assertEqual((doc.items[0].expense_account, doc.items[0].assignment_source), (self.account("6810"), "Library"))

	def test_only_expense_accounts_and_listing(self):
		bank = frappe.db.get_value("Account", {"company": self.company, "account_type": "Bank", "is_group": 0}, "name")
		with self.assertRaises(frappe.ValidationError):
			self.configure(expense_account=bank)
		self.configure(always_review=1)
		self.assertIn(SUPPLIER, [r["supplier"] for r in supplier_settings.list_settings()])
