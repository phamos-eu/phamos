# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The decision engine: checks, flags and the decision for a read receipt."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import decide
from phamos.api import accounting_receipts

SUPPLIER = "Decide Test Lieferant GmbH"


class DecideTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)
		self.company = frappe.defaults.get_global_default("company")
		self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.account = frappe.db.get_value("Account", {"company": self.company, "root_type": "Expense", "is_group": 0}, "name")

	def tearDown(self):
		frappe.db.rollback()

	def receipt(self, status=None, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Decide test",
				"company": self.company,
				"currency": self.currency,
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": values.pop("supplier_reference", frappe.generate_hash(length=8)),
				"posting_date": "2026-10-01",
				"sum": 100,
				"receipt_type": "Invoice",
				"items": [{"item_name": "Hosting", "qty": 1, "rate": 100, "amount": 100, "expense_account": self.account}],
				**values,
			}
		).insert(ignore_permissions=True)
		if status:
			doc.db_set("status", status)
		return doc

	def history(self, *amounts):
		for i, amount in enumerate(amounts):
			self.receipt(status="Sent to DATEV", sum=amount, posting_date=f"2026-0{1 + i}-15")

	def codes(self, result):
		return [f["code"] for f in result["flags"]]


class TestDecisions(DecideTestCase):
	def test_known_supplier_usual_amount_unpaid_is_ready_to_approve(self):
		self.history(100, 105, 98)
		result = decide.evaluate(self.receipt())
		self.assertEqual((result["decision"], result["confidence"], result["flags"]), ("approve_to_pay", 100, []))

	def test_paid_receipt_is_ready_for_datev(self):
		self.history(100, 105, 98)
		result = decide.evaluate(self.receipt(), extraction={"payment_status": "paid", "paid_with": "card"})
		self.assertEqual(result["decision"], "auto_datev")
		self.assertEqual(self.codes(result), ["says_paid"])

	def test_new_supplier_needs_a_person(self):
		result = decide.evaluate(self.receipt())
		self.assertEqual((result["decision"], self.codes(result)), ("needs_human", ["new_supplier"]))
		self.assertEqual(result["confidence"], 85)

	def test_unusual_amount(self):
		self.history(100, 105, 98, 101)
		result = decide.evaluate(self.receipt(sum=400))
		self.assertIn("unusual_amount", self.codes(result))
		self.assertIn("+", [f for f in result["flags"] if f["code"] == "unusual_amount"][0]["message"])

	def test_duplicates(self):
		self.history(100, 105, 98)
		self.receipt(supplier_reference="RE-2026-77")
		self.assertIn("duplicate", self.codes(decide.evaluate(self.receipt(supplier_reference="re 2026 77"))))
		near = decide.evaluate(self.receipt(sum=100, posting_date="2026-10-03"))
		self.assertIn("possible_duplicate", self.codes(near))

	def test_not_a_voucher_and_missing_data(self):
		self.history(100, 105, 98)
		self.assertEqual(decide.evaluate(self.receipt(receipt_type="Reminder"))["decision"], "not_a_voucher")
		result = decide.evaluate(self.receipt(supplier=None, supplier_reference=""))
		self.assertEqual(result["decision"], "needs_human")
		self.assertTrue({"no_supplier", "no_reference"} <= set(self.codes(result)))

	def test_totals_and_lines(self):
		self.history(100, 105, 98)
		doc = self.receipt(net_total=90, total_taxes=5)
		doc.items[0].expense_account = None
		codes = self.codes(decide.evaluate(doc))
		self.assertIn("totals_inconsistent", codes)
		self.assertIn("line_without_account", codes)
		self.assertNotIn("line_without_account", self.codes(decide.evaluate(doc, earlier_flags=[{"code": "account_unclear", "severity": "warn"}])))

	def test_earlier_warnings_make_it_a_human_decision(self):
		self.history(100, 105, 98)
		result = decide.evaluate(self.receipt(), earlier_flags=[{"code": "low_confidence", "severity": "warn", "message": "x"}])
		self.assertEqual((result["decision"], result["confidence"]), ("needs_human", 85))


class TestApplyAndQueue(DecideTestCase):
	def test_decision_is_stored_and_inbox_moves_to_needs_decision(self):
		self.history(100, 105, 98)
		doc = self.receipt()
		decide.apply_decision(doc, decide.evaluate(doc), decide.DEFAULT_PARAMS)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, ["status", "ai_decision"]), ("Needs Decision", "approve_to_pay"))

	def test_no_automatic_datev_unless_switched_on(self):
		self.history(100, 105, 98)
		doc = self.receipt(is_paid=1)
		result = decide.evaluate(doc)
		self.assertEqual(result["decision"], "auto_datev")
		decide.apply_decision(doc, result, decide.DEFAULT_PARAMS)
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "sent_to_datev"), 0)

	def test_queue_shows_the_suggestion(self):
		row = frappe._dict(name="AR-X", title="x", status="Needs Decision", ai_decision="auto_datev", due_date=None, is_paid=0)
		item = accounting_receipts._queue_row(row, "ready", [], frappe.utils.today())
		self.assertEqual(item["suggestion"], "AI: paid and clear, send to DATEV")
