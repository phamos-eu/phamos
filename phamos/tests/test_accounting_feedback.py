# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Learning from corrections: recorded on the run, turned into suggested reading rules."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.accounting import feedback
from phamos.ai_agents.context import AgentContext
from phamos.ai_agents.runner import prompt_rules
from phamos.api import ai_skills
from phamos.setup.accounting_receipt import ACCOUNTING_AGENT, ensure_accounting_receipt_setup

SUPPLIER = "Feedback Test Shop GmbH"
TEXT = "Musterladen\nBestellnr.: 12345\nRechnungsnr.: 98765\nDatum: 03.10.2026\nGesamt: 1.234,50 EUR"


class TestFeedback(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		ensure_accounting_receipt_setup()
		if not frappe.db.exists("Supplier", SUPPLIER):
			frappe.get_doc({"doctype": "Supplier", "supplier_name": SUPPLIER, "supplier_group": "Services"}).insert(ignore_permissions=True)
		frappe.db.delete("AI Skill", {"suggestion_key": ("like", f"{SUPPLIER}::%")})
		self.company = frappe.defaults.get_global_default("company")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def read_receipt(self, reference="12345", **values):
		"""A receipt as the AI left it: values set by a completed run."""
		doc = frappe.get_doc(
			{
				"doctype": "Accounting Receipt",
				"title": "Feedback test",
				"company": self.company,
				"currency": frappe.db.get_value("Company", self.company, "default_currency"),
				"conversion_rate": 1,
				"supplier": SUPPLIER,
				"supplier_reference": reference,
				"posting_date": "2026-10-03",
				"sum": 1234.5,
				**values,
			}
		).insert(ignore_permissions=True)
		run = frappe.get_doc(
			{
				"doctype": "AI Agent Run",
				"agent": ACCOUNTING_AGENT,
				"reference_doctype": "Accounting Receipt",
				"reference_name": doc.name,
				"status": "Completed",
				"fields_set": "supplier_reference, posting_date, sum",
				"analysis": frappe.as_json({"extraction": {"values": {"supplier_reference": reference, "posting_date": "2026-10-03", "sum": 1234.5}}}),
			}
		).insert(ignore_permissions=True)
		doc.db_set({"ai_run": run.name, "ai_document_text": TEXT})
		return frappe.get_doc("Accounting Receipt", doc.name), run

	def correct(self, doc, **values):
		doc.update(values)
		doc.save()
		return frappe.get_doc("AI Agent Run", doc.ai_run)

	def suggestion(self, field="supplier_reference"):
		return frappe.db.get_value("AI Skill", {"suggestion_key": f"{SUPPLIER}::{field}"},
			["name", "enabled", "origin", "occurrences", "dismissed"], as_dict=True)

	def test_label_before_finds_the_word_in_front_of_a_value(self):
		text = TEXT
		self.assertEqual(feedback.label_before(text, "supplier_reference", "98765"), "Rechnungsnr.")
		self.assertEqual(feedback.label_before(text, "supplier_reference", "12345"), "Bestellnr.")
		self.assertEqual(feedback.label_before(text, "posting_date", "2026-10-03"), "Datum")
		self.assertEqual(feedback.label_before(text, "sum", 1234.5), "Gesamt")
		self.assertIsNone(feedback.label_before(text, "supplier_reference", "nowhere"))

	def test_a_correction_is_recorded_and_a_rule_suggested(self):
		doc, _run = self.read_receipt()
		run = self.correct(doc, supplier_reference="98765")
		self.assertEqual(run.outcome, "Corrected")
		self.assertEqual(frappe.parse_json(run.corrections)[0]["human_value"], "98765")
		s = self.suggestion()
		self.assertEqual((s.enabled, s.origin, s.occurrences), (0, "Suggested", 1))
		action = frappe.db.get_value("AI Prompt Rule", {"parent": s.name}, "action")
		self.assertIn("Rechnungsnr.", action)
		self.assertIn("Bestellnr.", action)

	def test_the_same_correction_counts_up(self):
		first, _ = self.read_receipt()
		self.correct(first, supplier_reference="98765")
		second, _ = self.read_receipt()
		self.correct(second, supplier_reference="98765")
		self.assertEqual(self.suggestion().occurrences, 2)
		self.assertEqual(frappe.db.count("AI Skill", {"suggestion_key": f"{SUPPLIER}::supplier_reference"}), 1)

	def test_saving_again_does_not_count_twice(self):
		doc, _ = self.read_receipt()
		self.correct(doc, supplier_reference="98765")
		doc.reload()
		self.correct(doc, title="Just a title")
		self.assertEqual(self.suggestion().occurrences, 1)

	def test_dismissed_suggestions_stay_dismissed(self):
		doc, _ = self.read_receipt()
		self.correct(doc, supplier_reference="98765")
		ai_skills.dismiss_suggestion(self.suggestion().name)
		other, _ = self.read_receipt()
		self.correct(other, supplier_reference="98765")
		s = self.suggestion()
		self.assertEqual((s.dismissed, s.occurrences), (1, 1))
		self.assertFalse(ai_skills.get_learning()["suggestions"] and
			any(x.name == s.name for x in ai_skills.get_learning()["suggestions"]))

	def test_accepted_rules_reach_the_prompt_for_this_supplier(self):
		doc, _ = self.read_receipt()
		self.correct(doc, supplier_reference="98765")
		name = self.suggestion().name
		ai_skills.accept_suggestion(name)
		self.assertEqual(frappe.db.get_value("AI Skill", name, ["enabled", "origin"]), (1, "Learned"))
		agent = frappe.get_doc("AI Agent", ACCOUNTING_AGENT)
		ctx = AgentContext(run=None, agent=agent, doc=doc, party=("Supplier", SUPPLIER))
		self.assertTrue(any("Rechnungsnr." in (r.action or "") for r in prompt_rules(ctx, "Extract")))
		ctx_other = AgentContext(run=None, agent=agent, doc=doc, party=("Supplier", "Someone Else"))
		self.assertFalse(any("Rechnungsnr." in (r.action or "") for r in prompt_rules(ctx_other, "Extract")))

	def test_amount_and_date_corrections_and_unchanged_values(self):
		doc, _ = self.read_receipt()
		run = self.correct(doc, sum=1243.5, posting_date="2026-10-04")
		fields = sorted(c["field"] for c in frappe.parse_json(run.corrections))
		self.assertEqual(fields, ["posting_date", "sum"])
		untouched, _ = self.read_receipt()
		run = self.correct(untouched, title="Nothing the AI set")
		self.assertFalse(run.outcome)

	def test_accepted_when_approved_without_changes(self):
		doc, _ = self.read_receipt()
		run = self.correct(doc, status="Sent to DATEV")
		self.assertEqual(run.outcome, "Accepted")

	def test_the_ais_own_saves_are_not_corrections(self):
		doc, _ = self.read_receipt()
		frappe.set_user(feedback.ai_user())
		doc.supplier_reference = "OTHER"
		doc.save(ignore_permissions=True)
		frappe.set_user("Administrator")
		self.assertFalse(frappe.db.get_value("AI Agent Run", doc.ai_run, "outcome"))

	def test_learning_overview(self):
		doc, _ = self.read_receipt()
		self.correct(doc, supplier_reference="98765")
		learning = ai_skills.get_learning()
		self.assertIn(doc.name, [c["reference_name"] for c in learning["corrections"]], learning["corrections"])
		self.assertGreaterEqual(learning["by_field"]["supplier_reference"], 1)
		self.assertIn(self.suggestion().name, [s.name for s in learning["suggestions"]])
		self.assertNotIn(self.suggestion().name, [s.name for s in ai_skills.get_ai_skills()["skills"]])

	def test_backfill_finds_earlier_corrections_once(self):
		doc, _ = self.read_receipt()
		doc.db_set("supplier_reference", "98765")  # corrected before feedback existed
		first = feedback.backfill(days=30)
		self.assertGreaterEqual(first["corrected"], 1)
		self.assertEqual(frappe.db.get_value("AI Agent Run", doc.ai_run, "outcome"), "Corrected")
		feedback.backfill(days=30)
		self.assertEqual(self.suggestion().occurrences, 1)
