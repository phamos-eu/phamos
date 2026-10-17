# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Assignment library, learning and the account proposal for receipt lines."""

import json
import unittest
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import branching, classify, expense_accounts, library
from phamos.ai_agents import llm

SUPPLIER = "Library Test Telekom GmbH"
OTHER = "Library Test Other GmbH"


def skr04_company():
	for company in frappe.get_all("Company", pluck="name"):
		if expense_accounts.chart_family(company) == "SKR04":
			return company
	return None


class LibraryTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = skr04_company()
		if not self.company:
			raise unittest.SkipTest("needs a company with an SKR04 chart of accounts")
		expense_accounts.ensure_account_fields()
		for name in (SUPPLIER, OTHER):
			if not frappe.db.exists("Supplier", name):
				frappe.get_doc({"doctype": "Supplier", "supplier_name": name, "supplier_group": "Services"}).insert(ignore_permissions=True)
		frappe.db.delete("Account Assignment", {"company": self.company})
		expense_accounts.seed_expense_accounts(self.company, check_permission=False)
		self.ai_user = library.ai_user()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		expense_accounts.clear_account_cache()

	def account(self, number):
		return expense_accounts.account_by_number(self.company, number)

	def entry(self, description, number, supplier=SUPPLIER, validation="Confirmed", hits=1):
		name = library.learn(self.company, supplier, description, self.account(number), validation=validation, hits=hits)
		frappe.db.set_value("Account Assignment", name, "validation", validation)
		return name

	def receipt(self, lines, supplier=SUPPLIER, **values):
		return frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Library test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": supplier,
				"supplier_reference": "RE-LIB-1",
				"posting_date": "2026-10-01",
				"items": lines,
				**values,
			}
		).insert(ignore_permissions=True)

	def entry_of(self, description, number, supplier=SUPPLIER):
		return frappe.db.get_value(
			"Account Assignment",
			{"company": self.company, "supplier": supplier, "pattern": library.normalize_description(description),
			 "expense_account": self.account(number)},
			["name", "hits", "misses", "validation", "origin"],
			as_dict=True,
		)


class TestNormalization(unittest.TestCase):
	def test_descriptions_reduce_to_what_was_bought(self):
		cases = {
			"iCloud+ with 200 GB (Monthly)": "icloud+",
			"iCloud+ 2 TB (monthly)": "icloud+",
			"PROFESSIONAL SERVICES FOR SOFTWARE DEVELOPMENT, P-0155, USD 11": "professional services software development",
			"MagentaMobil M Business 10/2026": "magentamobil business",
			"Verbindungen zu 1&1": "verbindungen 1&1",
			"Mahngebühren": "mahngebuehren",
			"Super E5 Säule 3": "super e5 saeule",
		}
		for text, expected in cases.items():
			self.assertEqual(library.normalize_description(text), expected, text)


class TestMatching(LibraryTestCase):
	def test_tiers_supplier_global_other_and_fuzzy(self):
		self.entry("MagentaMobil M Business", "6805")
		top = library.find("MagentaMobil M Business 11/2026", SUPPLIER, self.company)[0]
		self.assertEqual((top["account"], top["score"], top["source"]), (self.account("6805"), 95, "Library"))
		self.assertEqual(library.find("MagentaMobil M Business", OTHER, self.company)[0]["score"], 85)
		self.entry("Domain registration", "6810", supplier=None)
		self.assertEqual(library.find("Domain registration", OTHER, self.company)[0]["score"], 90)
		fuzzy = library.find("MagentaMobil Busines", SUPPLIER, self.company)
		self.assertTrue(85 <= fuzzy[0]["score"] < 95, fuzzy)

	def test_ai_entries_need_acceptance_and_retired_entries_drop_out(self):
		ai = self.entry("Paketpreis", "6815", validation="AI", hits=0)
		self.assertEqual(library.find("Paketpreis", SUPPLIER, self.company)[0]["score"], 75)
		frappe.db.set_value("Account Assignment", ai, {"misses": 2, "hits": 0})
		self.assertFalse(library.find("Paketpreis", SUPPLIER, self.company))

	def test_two_accounts_with_equal_scores_are_unclear(self):
		self.entry("Wartung Server", "6495")
		self.entry("Wartung Server", "6810")
		self.assertEqual(library.find("Wartung Server", SUPPLIER, self.company)[0]["score"], 70)

	def test_supplier_usual_account(self):
		self.entry("Mobilfunk Rechnung", "6805", hits=2)
		self.entry("Festnetz Anschluss", "6805")
		top = library.find("Roaming EU Paket", SUPPLIER, self.company)[0]
		self.assertEqual((top["account"], top["source"], top["score"]), (self.account("6805"), "Supplier History", 85))

	def test_lowering_validation_needs_a_manager(self):
		name = self.entry("MagentaMobil", "6805")
		frappe.set_user(self.ai_user)
		doc = frappe.get_doc("Account Assignment", name)
		doc.validation = "AI"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)


class TestClassification(LibraryTestCase):
	def run_as_ai(self, doc, **params):
		frappe.set_user(self.ai_user)
		try:
			return classify.classify_receipt(frappe.get_doc("Accounting Receipt", doc.name), {**classify.DEFAULT_PARAMS, **params})
		finally:
			frappe.set_user("Administrator")

	def test_library_hit_assigns_without_asking_mistral(self):
		self.entry("MagentaMobil M Business", "6805")
		doc = self.receipt([{"item_name": "MagentaMobil M Business 11/2026", "qty": 1, "rate": 40, "amount": 40}])
		with patch.object(llm, "chat_json") as chat:
			result = self.run_as_ai(doc)
		chat.assert_not_called()
		row = frappe.get_doc("Accounting Receipt", doc.name).items[0]
		self.assertEqual((row.expense_account, row.assignment_source, row.ai_expense_account), (self.account("6805"), "Library", self.account("6805")))
		self.assertEqual(result["unclear"], 0)

	def test_mistral_picks_from_offered_accounts_and_is_stored_as_ai_entry(self):
		doc = self.receipt([{"item_name": "Glasfaser 500 Anschluss", "qty": 1, "rate": 50, "amount": 50}])
		answer = {"lines": [{"index": 1, "account_number": "6810", "confidence": 0.86, "reason": "Internetanschluss"}]}
		with patch.object(llm, "chat_json", return_value=(answer, "mistral-test")) as chat:
			result = self.run_as_ai(doc)
		self.assertIn("6810", chat.call_args.args[0])
		row = frappe.get_doc("Accounting Receipt", doc.name).items[0]
		self.assertEqual((row.expense_account, row.assignment_source, row.ai_confidence), (self.account("6810"), "AI", 86))
		self.assertEqual(frappe.db.get_value("Account Assignment", row.assignment, ["validation", "hits"]), ("AI", 0))
		self.assertEqual(result["llm_calls"], 1)

	def test_unsure_or_invalid_answers_leave_the_line_open_with_candidates(self):
		self.entry("Paket Versand", "6800", validation="AI", hits=0)
		doc = self.receipt([
			{"item_name": "Paket Versand", "qty": 1, "rate": 5, "amount": 5},
			{"item_name": "Irgendwas", "qty": 1, "rate": 5, "amount": 5},
		])
		answer = {"lines": [{"index": 1, "account_number": "6800", "confidence": 0.6, "reason": "Porto?"},
			{"index": 2, "account_number": "9999", "confidence": 0.99, "reason": "invented"}]}
		with patch.object(llm, "chat_json", return_value=(answer, "mistral-test")):
			result = self.run_as_ai(doc)
		rows = frappe.get_doc("Accounting Receipt", doc.name).items
		self.assertFalse(rows[0].expense_account or rows[1].expense_account)
		self.assertEqual(json.loads(rows[0].ai_candidates)[0]["account"], self.account("6800"))
		self.assertEqual(result["unclear"], 2)
		self.assertEqual([f["code"] for f in result["flags"]], ["account_unclear", "account_unclear"])

	def test_without_mistral_only_the_library_is_used(self):
		doc = self.receipt([{"item_name": "Unbekannt", "qty": 1, "rate": 5, "amount": 5}])
		with patch.object(llm, "chat_json", side_effect=llm.LLMNotConfigured("no key")):
			result = self.run_as_ai(doc)
		self.assertEqual(result["unclear"], 1)
		self.assertIn("Mistral", frappe.get_doc("Accounting Receipt", doc.name).items[0].ai_reason)

	def test_lines_with_an_account_are_never_touched(self):
		doc = self.receipt([{"item_name": "MagentaMobil", "qty": 1, "rate": 5, "amount": 5, "expense_account": self.account("6815")}])
		self.entry("MagentaMobil", "6805")
		with patch.object(llm, "chat_json") as chat:
			result = self.run_as_ai(doc)
		chat.assert_not_called()
		self.assertEqual(result["open"], 0)
		self.assertEqual(frappe.get_doc("Accounting Receipt", doc.name).items[0].expense_account, self.account("6815"))


class TestLearning(LibraryTestCase):
	def test_a_person_choosing_an_account_teaches_the_library_once(self):
		doc = self.receipt([{"item_name": "Toner schwarz", "qty": 1, "rate": 30, "amount": 30, "expense_account": self.account("6815")}])
		entry = self.entry_of("Toner schwarz", "6815")
		self.assertEqual((entry.validation, entry.origin, entry.hits), ("Confirmed", "Human", 1))
		self.assertEqual(doc.items[0].assignment_source, "Human")
		doc.reload()
		doc.title = "Saved again"
		doc.save()
		self.assertEqual(self.entry_of("Toner schwarz", "6815").hits, 1)

	def test_correcting_an_ai_proposal_records_a_miss(self):
		self.entry("Datenoption", "6810")
		doc = self.receipt([{"item_name": "Datenoption 20 GB", "qty": 1, "rate": 10, "amount": 10}])
		frappe.set_user(self.ai_user)
		classify.classify_receipt(frappe.get_doc("Accounting Receipt", doc.name), dict(classify.DEFAULT_PARAMS, use_llm=0))
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Accounting Receipt", doc.name)
		self.assertEqual(doc.items[0].assignment_source, "Library")
		doc.items[0].expense_account = self.account("6805")
		doc.save()
		self.assertEqual(self.entry_of("Datenoption", "6810").misses, 1)
		self.assertEqual(self.entry_of("Datenoption", "6805").validation, "Confirmed")
		self.assertEqual(doc.items[0].assignment_source, "Human")

	def test_accepted_ai_proposals_count_when_the_receipt_is_invoiced(self):
		self.entry("Datenoption", "6810")
		doc = self.receipt([{"item_name": "Datenoption 20 GB", "qty": 1, "rate": 10, "amount": 10, "tax_rate": 19}])
		frappe.set_user(self.ai_user)
		classify.classify_receipt(frappe.get_doc("Accounting Receipt", doc.name), dict(classify.DEFAULT_PARAMS, use_llm=0))
		frappe.set_user("Administrator")
		pi = branching.make_purchase_invoice(frappe.get_doc("Accounting Receipt", doc.name))
		pi.submit()
		self.assertEqual(self.entry_of("Datenoption", "6810").hits, 2)
		self.assertEqual(frappe.get_doc("Accounting Receipt", doc.name).items[0].learned_account, self.account("6810"))

	def test_invoices_booked_in_desk_and_the_history_import(self):
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": self.company,
				"supplier": OTHER,
				"posting_date": "2026-10-01",
				"set_posting_time": 1,
				"items": [{"item_name": "Hetzner Cloud CX22", "description": "Hetzner Cloud CX22", "qty": 1, "rate": 5,
					"uom": "Nos", "conversion_factor": 1, "expense_account": self.account("6810")}],
			}
		)
		pi.set_missing_values()
		pi.items[0].expense_account = self.account("6810")
		pi.insert()
		pi.submit()
		entry = self.entry_of("Hetzner Cloud CX22", "6810", supplier=OTHER)
		self.assertEqual((entry.origin, entry.validation, entry.hits), ("History", "Confirmed", 1))
		first = library.rebuild_from_history(self.company, months=1)
		again = library.rebuild_from_history(self.company, months=1)
		self.assertGreaterEqual(first["invoice_lines"], 1)
		self.assertEqual(again["created"], 0)
		self.assertEqual(self.entry_of("Hetzner Cloud CX22", "6810", supplier=OTHER).hits, 1)
