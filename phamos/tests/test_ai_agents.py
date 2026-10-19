# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""AI agent framework and receipt extraction v2 (Mistral is always mocked)."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.file_manager import save_file

from phamos.accounting import extraction
from phamos.ai_agents import runner
from phamos.api import accounting_receipts, accounting_spa
from phamos.patches.v1_0 import move_ai_prompt_rules_to_ai_skill
from phamos.setup.accounting_receipt import ACCOUNTING_AGENT, ensure_accounting_receipt_setup, ensure_extract_skill
from phamos.tests.test_accounting_receipt_intake import blank_pdf

SUPPLIER = "AI Test Lieferant GmbH"
ANSWER = {
	"receipt_type": "Invoice",
	"invoice_number": "RE-2026-100",
	"invoice_date": "2026-10-01",
	"due_date": "2026-10-15",
	"supplier_name": SUPPLIER,
	"supplier_tax_id": "DE999999999",
	"currency": "EUR",
	"total_gross": "119,00",
	"total_net": 100,
	"total_tax": 19,
	"payment_status": "unpaid",
	"items": [{"description": "Beratung", "quantity": 2, "unit_price": "50,00", "amount": 100, "tax_rate": 19}],
	"confidence": {"invoice_number": 0.95, "invoice_date": 0.99, "supplier_name": 0.9, "total_gross": 0.99},
}


class AgentTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_accounting_receipt_setup()
		# These tests are about reading the PDF; the account proposal has its own tests.
		for handler in ("classify_lines", "decide_receipt"):
			frappe.db.set_value("AI Skill", {"agent": ACCOUNTING_AGENT, "handler": handler}, "enabled", 0)
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(
				ignore_permissions=True
			)
		self.ocr = patch("phamos.ai_agents.llm.ocr_pdf", return_value="Rechnung RE-2026-100 ...").start()
		self.chat = patch("phamos.ai_agents.llm.chat_json", side_effect=lambda *a, **k: (dict(ANSWER), "mistral-test")).start()
		patch("phamos.ai_agents.runner.frappe.publish_realtime").start()

	def tearDown(self):
		patch.stopall()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def receipt(self, **values):
		doc = frappe.get_doc({"doctype": "Accounting Receipt", "title": "Test", "currency": "EUR", "conversion_rate": 1, **values})
		doc.insert(ignore_permissions=True)
		url = save_file(f"{doc.name}.pdf", blank_pdf(), "Accounting Receipt", doc.name, is_private=1).file_url
		doc.db_set("attachment", url)
		return doc

	def run_agent(self, doc, mode="Fill Empty"):
		run = runner.run_now("Accounting Receipt", doc.name, mode=mode)
		self.assertEqual(run.status, "Completed", run.error)
		return run, frappe.get_doc("Accounting Receipt", doc.name)


class TestExtractionRun(AgentTestCase):
	def test_fills_empty_fields_items_and_mirrors_the_result(self):
		run, doc = self.run_agent(self.receipt())
		self.assertEqual(doc.supplier_reference, "RE-2026-100")
		self.assertEqual(doc.supplier, SUPPLIER)
		self.assertEqual(doc.sum, 119)
		self.assertEqual(str(doc.due_date), "2026-10-15")
		self.assertEqual([(i.item_name, i.qty, i.rate) for i in doc.items], [("Beratung", 2, 50)])
		self.assertEqual(doc.ai_run, run.name)
		self.assertIn("RE-2026-100", doc.ai_summary)
		self.assertAlmostEqual(doc.ai_confidence, 95.8, places=1)
		self.assertIn("supplier_reference", run.fields_set)
		self.assertEqual(run.llm_calls, 2)

	def test_after_reading_the_lines_get_an_expense_account(self):
		from phamos.accounting import expense_accounts

		receipt = self.receipt()
		company = frappe.db.get_value("Accounting Receipt", receipt.name, "company")
		if expense_accounts.chart_family(company) != "SKR04":
			self.skipTest("needs an SKR04 company")
		expense_accounts.seed_expense_accounts(company, check_permission=False)
		frappe.db.set_value("AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "classify_lines"}, "enabled", 1)
		proposal = {"lines": [{"index": 1, "account_number": "6303", "confidence": 0.9, "reason": "Beratung ist Fremdleistung"}]}
		self.chat.side_effect = lambda prompt, *a, **k: (
			(proposal if prompt.startswith("Assign each invoice line") else dict(ANSWER)), "mistral-test"
		)
		run, doc = self.run_agent(receipt)
		steps = {s["phase"]: s["status"] for s in json.loads(run.steps)}
		self.assertEqual(steps.get("Classify"), "Passed")
		self.assertEqual(frappe.db.get_value("Account", doc.items[0].expense_account, "account_number"), "6303")
		self.assertEqual(doc.items[0].assignment_source, "AI")

	def test_values_a_human_set_are_kept(self):
		_run, doc = self.run_agent(self.receipt(supplier_reference="MY-REF", sum=50))
		self.assertEqual(doc.supplier_reference, "MY-REF")
		self.assertEqual(doc.sum, 50)
		self.assertEqual(doc.posting_date.isoformat(), "2026-10-01")  # empty before, so filled

	def test_overwrite_mode_replaces_values(self):
		_run, doc = self.run_agent(self.receipt(supplier_reference="MY-REF"), mode="Overwrite")
		self.assertEqual(doc.supplier_reference, "RE-2026-100")

	def test_ai_never_fills_the_note_or_system_fields(self):
		self.chat.side_effect = lambda *a, **k: ({**ANSWER, "note": "x", "sent_to_datev": 1, "company": "x"}, "m")
		_run, doc = self.run_agent(self.receipt())
		self.assertFalse(doc.note)
		self.assertEqual(doc.sent_to_datev, 0)

	def test_changes_are_recorded_under_the_ai_user(self):
		doc = self.receipt()
		self.run_agent(doc)
		owner = frappe.db.get_value("Version", {"ref_doctype": "Accounting Receipt", "docname": doc.name}, "owner",
			order_by="creation desc")
		self.assertEqual(owner, frappe.db.get_value("AI Agent", ACCOUNTING_AGENT, "user"))

	def test_second_run_reuses_the_ocr_text(self):
		doc = self.receipt()
		self.run_agent(doc)
		self.run_agent(doc, mode="Overwrite")
		self.assertEqual(self.ocr.call_count, 1)

	def test_unknown_supplier_is_flagged_not_guessed(self):
		self.chat.side_effect = lambda *a, **k: ({**ANSWER, "supplier_name": "AI Test", "supplier_tax_id": None}, "m")
		run, doc = self.run_agent(self.receipt())
		self.assertFalse(doc.supplier)
		self.assertIn("supplier_unknown", [f["code"] for f in json.loads(run.run_flags)])

	def test_own_company_is_never_the_supplier(self):
		doc = frappe._dict(company="phamos")
		with patch.object(extraction, "resolve_link_for_extract", return_value="phamos"):
			values, *_ = extraction.map_answer({"supplier_name": "phamos"}, doc)
		self.assertNotIn("supplier", values)

	def test_currency_default_is_replaced_on_first_read_only(self):
		company = frappe.db.get_value("Company", {}, "name")
		self.chat.side_effect = lambda *a, **k: ({**ANSWER, "currency": "USD"}, "m")
		_run, doc = self.run_agent(self.receipt(company=company, currency=frappe.db.get_value("Company", company, "default_currency")))
		self.assertEqual(doc.currency, "USD")
		_run, doc = self.run_agent(doc)
		self.assertEqual(doc.currency, "USD")

	def test_prompt_carries_the_invoice_number_rule_and_rules(self):
		prompt = extraction.build_prompt("TEXT", [frappe._dict(case_description="Apple", action="take Document No.")], "phamos")
		self.assertIn("NEVER an order number", prompt)
		self.assertIn("phamos is never the supplier", prompt)
		self.assertIn("When: Apple", prompt)


class TestSkills(AgentTestCase):
	def add_skill(self, **values):
		return frappe.get_doc({"doctype": "AI Skill", "agent": ACCOUNTING_AGENT, "enabled": 1, "phase": "Extract", **values}).insert(
			ignore_permissions=True
		)

	def test_supplier_rules_trigger_a_second_read_with_them(self):
		self.add_skill(skill_name="Supplier rule", party_doctype="Supplier", party=SUPPLIER,
			prompt_rules=[{"enabled": 1, "order": 1, "case_description": "Invoice of this supplier", "action": "Use the number after Beleg"}])
		run, _doc = self.run_agent(self.receipt())
		self.assertEqual(self.chat.call_count, 2)
		self.assertIn("Use the number after Beleg", self.chat.call_args_list[1].args[0])
		self.assertNotIn("Use the number after Beleg", self.chat.call_args_list[0].args[0])
		self.assertEqual(run.llm_calls, 3)

	def test_rules_of_other_suppliers_and_false_conditions_are_ignored(self):
		other = frappe.get_doc({"doctype": "Supplier", "supplier_name": "Other AI Supplier", "supplier_group": "Services"}).insert(ignore_permissions=True)
		self.add_skill(skill_name="Other", party_doctype="Supplier", party=other.name,
			prompt_rules=[{"enabled": 1, "case_description": "x", "action": "RULE-OTHER"}])
		self.add_skill(skill_name="Big only", condition="doc.sum > 1000000",
			prompt_rules=[{"enabled": 1, "case_description": "x", "action": "RULE-BIG"}])
		self.run_agent(self.receipt())
		prompts = " ".join(call.args[0] for call in self.chat.call_args_list)
		self.assertNotIn("RULE-OTHER", prompts)
		self.assertNotIn("RULE-BIG", prompts)
		self.assertEqual(self.chat.call_count, 1)

	def test_invalid_condition_and_unknown_handler_are_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self.add_skill(skill_name="Bad", condition="doc.sum >")
		with self.assertRaises(frappe.ValidationError):
			self.add_skill(skill_name="Bad handler", handler="does_not_exist")

	def test_gated_skill_is_skipped_when_an_earlier_phase_failed(self):
		self.chat.side_effect = Exception("Mistral down")
		ensure = frappe.get_doc("AI Skill", ensure_extract_skill())
		ensure.db_set("on_fail", "Continue")
		self.add_skill(skill_name="Gated read", phase="Decide", handler="extract_document", gate_on_previous=1)
		run = runner.run_now("Accounting Receipt", self.receipt().name)
		steps = json.loads(run.steps)
		self.assertEqual([s["status"] for s in steps], ["Error", "Skipped"])


class TestMigrationAndCockpit(AgentTestCase):
	def test_old_prompt_rules_move_to_the_extract_skill_once(self):
		skill = frappe.get_doc("AI Skill", ensure_extract_skill())
		skill.set("prompt_rules", [])
		skill.save(ignore_permissions=True)
		config = frappe.get_single("AI Prompt Configuration")
		config.set("rules", [{"enabled": 1, "order": 1, "case_description": "Old case", "action": "Old action", "reason": "why"}])
		config.save(ignore_permissions=True)
		move_ai_prompt_rules_to_ai_skill.execute()
		move_ai_prompt_rules_to_ai_skill.execute()
		rules = frappe.get_doc("AI Skill", skill.name).prompt_rules
		self.assertEqual([(r.case_description, r.reason) for r in rules], [("Old case", "why")])

	def test_diff_lists_differences_and_apply_takes_them_over(self):
		doc = self.receipt(supplier_reference="MY-REF")
		self.run_agent(doc)
		diff = accounting_receipts.get_extraction_diff(doc.name)
		rows = {r["fieldname"]: r for r in diff["rows"]}
		self.assertEqual(rows["supplier_reference"]["state"], "different")
		self.assertNotIn("sum", rows)  # filled by the run, so equal now
		accounting_receipts.apply_extraction(doc.name, fields=["supplier_reference"])
		self.assertEqual(frappe.db.get_value("Accounting Receipt", doc.name, "supplier_reference"), "RE-2026-100")

	def test_cockpit_state_comes_from_the_latest_run(self):
		doc = self.receipt()
		self.assertEqual(accounting_spa.get_receipt_extract_status(doc.name), {"status": "idle"})
		self.run_agent(doc)
		state = accounting_spa.get_receipt_extract_status(doc.name)
		self.assertEqual(state["status"], "done")
		self.assertIn("items", state["updated"])
		detail = accounting_spa.get_receipt(doc.name)
		self.assertEqual(detail["items"][0]["item_name"], "Beratung")
		self.assertEqual(detail["ai"]["summary"], frappe.db.get_value("Accounting Receipt", doc.name, "ai_summary"))
