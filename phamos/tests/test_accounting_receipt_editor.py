# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Editing receipts and creating suppliers from the Accounting Cockpit."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from phamos.api import accounting_receipts as api

SUPPLIER = "Editor Test Lieferant GmbH"


def make_receipt(**values):
	return frappe.get_doc(
		{"doctype": "Accounting Receipt", "title": "Editor test", "currency": "EUR", "conversion_rate": 1, **values}
	).insert(ignore_permissions=True)


class TestUpdateReceipt(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_saves_whitelisted_fields_and_returns_the_cockpit_view(self):
		doc = make_receipt()
		result = api.update_receipt(doc.name, supplier_reference="RE-1", sum=119, posting_date="2026-10-01", project="")
		self.assertEqual(result["supplier_reference"], "RE-1")
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "sum"), 119)
		self.assertIn("items", result)

	def test_unknown_and_system_fields_are_refused(self):
		doc = make_receipt()
		for field in ("status", "sent_to_datev", "ai_summary", "nonsense"):
			with self.assertRaises(frappe.ValidationError):
				api.update_receipt(doc.name, **{field: "x"})

	def test_empty_title_and_cancelled_receipts_are_refused(self):
		doc = make_receipt()
		with self.assertRaises(frappe.ValidationError):
			api.update_receipt(doc.name, title="  ")
		cancelled = make_receipt(status="Cancelled", cancel_reason="Other")
		with self.assertRaises(frappe.ValidationError):
			api.update_receipt(cancelled.name, supplier_reference="x")

	def test_stale_edit_raises_a_timestamp_conflict(self):
		doc = make_receipt()
		stale = add_to_date(now_datetime(), minutes=-5)
		with self.assertRaises(frappe.TimestampMismatchError):
			api.update_receipt(doc.name, modified=str(stale), supplier_reference="late")

	def test_item_lines_keep_names_compute_amounts_and_drop_empty_rows(self):
		doc = make_receipt(items=[{"item_name": "A", "qty": 1, "rate": 10, "amount": 10}, {"item_name": "B", "qty": 1, "rate": 5, "amount": 5}])
		keep = doc.items[0].name
		api.update_receipt(
			doc.name,
			items=[{"name": keep, "item_name": "A renamed", "qty": 2, "rate": 10}, {"item_name": "C", "qty": 3, "rate": 2}, {"item_name": " "}],
		)
		doc.reload()
		self.assertEqual([(r.item_name, r.qty, r.amount) for r in doc.items], [("A renamed", 2, 20), ("C", 3, 6)])
		self.assertEqual(doc.items[0].name, keep)

	def test_write_permission_is_required(self):
		doc = make_receipt()
		with patch.object(api.frappe.model.document.Document, "check_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				api.update_receipt(doc.name, supplier_reference="x")


class TestSuppliers(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.existing = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "Testfirma Apfel Vertrieb International Ltd.", "supplier_group": "Services", "tax_id": "IE0000000T"}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_suggestions_by_vat_id_and_name_without_legal_form(self):
		doc = make_receipt(supplier_tax_id="IE 0000000T")
		with patch.object(api, "_latest_extraction", return_value=("run", {"supplier_name": "Testfirma Apfel Vertrieb Limited"})):
			result = api.get_supplier_suggestions(doc.name)
		self.assertEqual(result["extracted"]["supplier_name"], "Testfirma Apfel Vertrieb Limited")
		top = result["candidates"][0]
		self.assertEqual(top["supplier"], self.existing.name)
		self.assertEqual(top["score"], 100)
		self.assertIn("same VAT ID", top["reasons"])

	def test_suggestion_by_iban_of_a_supplier_bank_account(self):
		frappe.get_doc({"doctype": "Bank", "bank_name": "Editor Test Bank"}).insert(ignore_permissions=True)
		frappe.get_doc(
			{"doctype": "Bank Account", "account_name": "Apple", "bank": "Editor Test Bank", "party_type": "Supplier",
			 "party": self.existing.name, "iban": "DE89370400440532013000"}
		).insert(ignore_permissions=True)
		doc = make_receipt(supplier_iban="DE89370400440532013000")
		with patch.object(api, "_latest_extraction", return_value=(None, None)):
			result = api.get_supplier_suggestions(doc.name)
		self.assertIn("same IBAN", result["candidates"][0]["reasons"])

	def test_create_supplier_with_address_and_bank_account(self):
		doc = make_receipt()
		with patch.object(api.frappe.db, "count", return_value=0):
			result = api.create_supplier_from_receipt(
				doc.name, SUPPLIER, tax_id="DE 123 456 789", country="Germany", address_line1="Hauptstr. 1",
				pincode="72070", city="Tübingen", iban="DE89 3704 0044 0532 0130 00",
			)
		supplier = frappe.get_doc("Supplier", result["supplier"])
		self.assertEqual(supplier.supplier_name, SUPPLIER)
		self.assertEqual(supplier.tax_id, "DE123456789")
		self.assertTrue(supplier.supplier_primary_address)
		account = frappe.get_doc("Bank Account", {"party": supplier.name})
		self.assertEqual(account.iban, "DE89370400440532013000")
		self.assertEqual(account.is_default, 1)
		self.assertEqual(account.bank, "BLZ 37040044")
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "supplier"), supplier.name)

	def test_existing_supplier_and_missing_tax_category_are_refused(self):
		doc = make_receipt()
		with self.assertRaises(frappe.ValidationError):
			api.create_supplier_from_receipt(doc.name, "Testfirma Apfel Vertrieb International Ltd.")
		with patch.object(api.frappe.db, "count", return_value=3), self.assertRaises(frappe.ValidationError):
			api.create_supplier_from_receipt(doc.name, SUPPLIER)
