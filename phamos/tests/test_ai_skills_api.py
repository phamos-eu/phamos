# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The cockpit API for AI skills: list, edit, dry run, run history."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import ai_skills
from phamos.setup.accounting_receipt import ACCOUNTING_AGENT, ensure_accounting_receipt_setup

SUPPLIER = "Skills API Test GmbH"


class TestAiSkillsApi(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_accounting_receipt_setup()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)
		self.decide = frappe.db.get_value("AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "decide_receipt"}, "name")
		self.classify = frappe.db.get_value("AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "classify_lines"}, "name")
		self.extract = frappe.db.get_value("AI Skill", {"agent": ACCOUNTING_AGENT, "handler": "extract_document", "party": ("is", "not set")}, "name")
		self.company = frappe.defaults.get_global_default("company")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def receipt(self, **values):
		return frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Skills API test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": "SK-1",
				"posting_date": "2026-10-01",
				"sum": 50,
				"items": [{"item_name": "Server Miete", "qty": 1, "rate": 50, "amount": 50}],
				**values,
			}
		).insert(ignore_permissions=True)

	def test_overview_lists_skills_by_phase_with_stats(self):
		doc = self.receipt()
		frappe.get_doc({"doctype": "AI Agent Run", "agent": ACCOUNTING_AGENT, "reference_doctype": "Accounting Receipt",
			"reference_name": doc.name, "status": "Completed", "steps": frappe.as_json([
				{"skill": self.decide, "status": "Passed"}, {"skill": self.classify, "status": "Uncertain"}])}).insert(ignore_permissions=True)
		overview = ai_skills.get_ai_skills()
		by_name = {s.name: s for s in overview["skills"]}
		self.assertIn("Decide", overview["phases"])
		self.assertGreaterEqual(by_name[self.decide]["stats"]["Passed"], 1)
		self.assertGreaterEqual(by_name[self.classify]["stats"]["Uncertain"], 1)
		self.assertEqual(overview["can_write"], 1)

	def test_editor_shows_params_as_fields_with_defaults(self):
		skill = ai_skills.get_ai_skill(self.decide)
		keys = [f["key"] for f in skill["param_fields"]]
		self.assertIn("auto_datev", keys)
		self.assertEqual(skill["params"]["auto_datev"], 0)
		self.assertEqual(skill["has_dry_run"], 1)

	def test_save_checks_ranges_and_replaces_rules(self):
		skill = ai_skills.get_ai_skill(self.decide)
		with self.assertRaises(frappe.ValidationError):
			ai_skills.save_ai_skill(self.decide, {"params": {**skill["params"], "min_history": 999}}, skill["modified"])
		saved = ai_skills.save_ai_skill(self.decide, {"params": {**skill["params"], "min_history": 5}}, skill["modified"])
		self.assertEqual(saved["params"]["min_history"], 5)
		rules = ai_skills.save_ai_skill(self.extract, {"prompt_rules": [
			{"enabled": 1, "case_description": "Apple invoices", "action": "Take the number after Document"},
			{"enabled": 1, "case_description": "", "action": ""}]})
		self.assertEqual([r["action"] for r in rules["prompt_rules"]], ["Take the number after Document"])

	def test_stale_save_is_refused(self):
		skill = ai_skills.get_ai_skill(self.decide)
		ai_skills.save_ai_skill(self.decide, {"description": "first"}, skill["modified"])
		with self.assertRaises(frappe.ValidationError):
			ai_skills.save_ai_skill(self.decide, {"description": "second"}, skill["modified"])

	def test_enable_toggle(self):
		ai_skills.set_skill_enabled(self.classify, 0)
		self.assertEqual(frappe.db.get_value("AI Skill", self.classify, "enabled"), 0)

	def test_dry_runs_change_nothing(self):
		doc = self.receipt()
		before = frappe.db.get_value("Accounting Receipt", doc.name, ["status", "ai_decision", "modified"], as_dict=True)
		decided = ai_skills.dry_run_ai_skill(self.decide, doc.name, params={"min_history": 0})
		self.assertEqual(decided["kind"], "decide")
		self.assertNotIn("new_supplier", [f["code"] for f in decided["flags"]])
		strict = ai_skills.dry_run_ai_skill(self.decide, doc.name, params={"min_history": 3})
		self.assertIn("new_supplier", [f["code"] for f in strict["flags"]])
		classified = ai_skills.dry_run_ai_skill(self.classify, doc.name)
		self.assertEqual((classified["kind"], classified["open"]), ("classify", 1))
		prompt = ai_skills.dry_run_ai_skill(self.extract, doc.name, prompt_rules=[{"enabled": 1, "case_description": "Hetzner",
			"action": "Use the Rechnungsnummer"}])
		self.assertIn("Use the Rechnungsnummer", prompt["prompt"])
		after = frappe.db.get_value("Accounting Receipt", doc.name, ["status", "ai_decision", "modified"], as_dict=True)
		self.assertEqual(before, after)
		self.assertFalse(frappe.db.get_value("Accounting Receipt Item", {"parent": doc.name}, "expense_account"))

	def test_runs_list_and_detail(self):
		doc = self.receipt()
		run = frappe.get_doc({"doctype": "AI Agent Run", "agent": ACCOUNTING_AGENT, "reference_doctype": "Accounting Receipt",
			"reference_name": doc.name, "status": "Completed", "decision": "needs_human",
			"run_flags": frappe.as_json([{"code": "new_supplier", "severity": "warn", "message": "New"}]),
			"steps": frappe.as_json([{"skill": self.decide, "skill_name": "Decide next step", "status": "Passed"}])}).insert(ignore_permissions=True)
		rows = ai_skills.get_agent_runs(reference_name=doc.name)
		self.assertEqual((rows[0]["name"], rows[0]["flag_count"]), (run.name, 1))
		detail = ai_skills.get_agent_run(run.name)
		self.assertEqual(detail["steps"][0]["skill_name"], "Decide next step")

	def test_read_only_users_cannot_save(self):
		email = "skills-reader@example.com"
		if not frappe.db.exists("User", email):
			frappe.get_doc({"doctype": "User", "email": email, "first_name": "Reader", "send_welcome_email": 0,
				"roles": [{"role": "Accounts User"}]}).insert(ignore_permissions=True)
		frappe.set_user(email)
		self.assertEqual(ai_skills.get_ai_skills()["can_write"], 0)
		with self.assertRaises(frappe.PermissionError):
			ai_skills.save_ai_skill(self.decide, {"description": "x"})
