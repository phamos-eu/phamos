# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""FAQ section of the Web Profile pages (phamos/phamos#1823).

Questions of the page language only (no fallback), in table order, collapsed <details> on the
page and the same rows as FAQPage JSON-LD. Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile_faq
"""

import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response_content

from phamos.web_profile.page import faq_schema
from phamos.web_profile.sections import build_profile, find_item

INDUSTRY = "WP FAQ Test Industry"
CUSTOMER = "WP FAQ Test Kunde GmbH"


def _reset_items():
	frappe.local.web_profile_items = None
	frappe.cache.delete_value("web_profile_items")


def _render(path):
	"""The page as a crawler gets it: as Guest, without a session."""
	frappe.set_user("Guest")
	set_request(method="GET", path=path)
	try:
		return get_response_content(path)
	finally:
		frappe.set_user("Administrator")


def _jsonld(html):
	blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
	return [entry for block in blocks for entry in json.loads(block)]


class TestWebProfileFaq(FrappeTestCase):
	def setUp(self):
		frappe.local.lang = "en"
		frappe.db.savepoint("web_profile_faq_test")
		if not frappe.db.exists("Industry Type", INDUSTRY):
			frappe.get_doc({"doctype": "Industry Type", "industry": INDUSTRY}).insert(ignore_permissions=True)
		self.industry = frappe.get_doc({
			"doctype": "Industry Web Profile", "industry": INDUSTRY, "published": 1,
			"faqs": [
				{"language": "de", "question": "Wie lange dauert es?", "answer": "<p>Drei Monate.</p>"},
				{"language": "en", "question": "How long does it take?", "answer": "<p>Three <b>months</b>.</p>"},
				{"language": "en", "question": "What does it cost?", "answer": "<p>It depends.</p>"},
				{"language": "fr", "question": "Combien ?", "answer": "<p>Ça dépend.</p>"},
			],
		}).insert(ignore_permissions=True)
		_reset_items()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.local.request = None  # page renders leave a request behind, which switches rate limits on
		frappe.db.rollback(save_point="web_profile_faq_test")
		_reset_items()

	def _profile(self, section, route, lang):
		_reset_items()
		return build_profile(find_item(section, route, lang), lang)

	def test_only_the_page_language_in_table_order(self):
		en = self._profile("industries", self.industry.route, "en")["faqs"]
		self.assertEqual([f.question for f in en], ["How long does it take?", "What does it cost?"])
		de = self._profile("industries", self.industry.route, "de")["faqs"]
		self.assertEqual([f.question for f in de], ["Wie lange dauert es?"])

	def test_no_fallback_to_german(self):
		doc = frappe.get_doc("Industry Web Profile", self.industry.name)
		doc.faqs = [row for row in doc.faqs if row.language == "de"]
		doc.save(ignore_permissions=True)
		faqs = self._profile("industries", self.industry.route, "en")["faqs"]
		self.assertEqual(faqs, [])
		self.assertIsNone(faq_schema(faqs))

	def test_rows_without_answer_text_are_left_out(self):
		for empty in ("<p><br></p>", "<p>&nbsp;</p>", "<p>\u00a0 </p>"):
			frappe.db.set_value("Web Profile FAQ", {"parent": self.industry.name, "question": "What does it cost?"},
				"answer", empty)
			faqs = self._profile("industries", self.industry.route, "en")["faqs"]
			self.assertEqual([f.question for f in faqs], ["How long does it take?"], empty)

	def test_faq_schema_has_every_question_and_answer(self):
		schema = faq_schema(self._profile("industries", self.industry.route, "en")["faqs"])
		self.assertEqual(schema["@type"], "FAQPage")
		self.assertEqual(
			[(q["@type"], q["name"], q["acceptedAnswer"]["text"]) for q in schema["mainEntity"]],
			[("Question", "How long does it take?", "<p>Three <b>months</b>.</p>"),
				("Question", "What does it cost?", "<p>It depends.</p>")])

	def test_page_shows_collapsed_questions_and_faqpage_jsonld(self):
		html = _render(find_item("industries", self.industry.route, "en").url)
		self.assertIn('class="wp-faq"', html)
		self.assertEqual(html.count('<details class="wp-faq-item">'), 2)  # no "open": all collapsed
		self.assertIn("Three <b>months</b>.", html)
		self.assertNotIn("Wie lange dauert es?", html)
		faq = next(e for e in _jsonld(html) if e.get("@type") == "FAQPage")
		self.assertEqual([q["name"] for q in faq["mainEntity"]], ["How long does it take?", "What does it cost?"])

	def test_page_without_questions_in_its_language_has_no_faq(self):
		doc = frappe.get_doc("Industry Web Profile", self.industry.name)
		doc.faqs = [row for row in doc.faqs if row.language != "en"]
		doc.save(ignore_permissions=True)
		_reset_items()
		html = _render(find_item("industries", self.industry.route, "en").url)
		self.assertNotIn('class="wp-faq"', html)
		self.assertFalse([e for e in _jsonld(html) if e.get("@type") == "FAQPage"])

	def test_anonymous_page_shows_its_faq(self):
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc({
				"doctype": "Customer", "customer_name": CUSTOMER, "customer_type": "Company",
				"customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}) or "All Customer Groups",
				"territory": frappe.db.get_value("Territory", {"is_group": 0}) or "All Territories",
			}).insert(ignore_permissions=True)
		stakeholder = frappe.get_doc({
			"doctype": "Stakeholder Web Profile", "stakeholder_type": "Customer", "party_type": "Customer",
			"party": CUSTOMER, "publish_as": "Anonymous", "region": "DACH", "published": 1,
			"faqs": [{"language": "en", "question": "Which modules?", "answer": "<p>Accounting.</p>"}],
		}).insert(ignore_permissions=True)
		_reset_items()
		item = find_item("customers", stakeholder.route, "en")
		self.assertTrue(item.masked)
		self.assertEqual([f.question for f in build_profile(item, "en")["faqs"]], ["Which modules?"])

	def test_every_web_profile_doctype_has_the_faq_table(self):
		from phamos.web_profile.sections import SECTIONS

		doctypes = {s["doctype"] for s in SECTIONS.values() if s["doctype"].endswith("Web Profile")}
		self.assertEqual(len(doctypes), 7)
		for doctype in doctypes:
			field = frappe.get_meta(doctype).get_field("faqs")
			self.assertEqual((field.fieldtype, field.options), ("Table", "Web Profile FAQ"), doctype)
