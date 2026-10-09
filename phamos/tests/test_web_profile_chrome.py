# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Language-aware navbar/footer and the DIN 5008 footer of the website (phamos/phamos#1502).

Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile_chrome
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.web_profile import chrome


class TestWebProfileChrome(FrappeTestCase):
	def setUp(self):
		frappe.local.lang = "de"
		frappe.local.wp_company_footer = None
		frappe.db.savepoint("web_profile_chrome_test")

	def tearDown(self):
		frappe.db.rollback(save_point="web_profile_chrome_test")
		frappe.local.wp_company_footer = None

	# --- IBAN ------------------------------------------------------------------------------------

	def test_iban_shows_only_country_check_digits_and_last_four(self):
		self.assertEqual(chrome.mask_iban("DE37 1203 0000 1077 0323 71"), "DE37 **** **** **** **23 71")
		self.assertEqual(chrome.mask_iban("de37120300001077032371"), "DE37 **** **** **** **23 71")

	def test_short_or_empty_iban_is_not_padded(self):
		self.assertEqual(chrome.mask_iban(""), "")
		self.assertEqual(chrome.mask_iban(None), "")

	# --- URL translation ---------------------------------------------------------------------------

	def test_section_urls_are_swapped_to_the_page_language(self):
		self.assertEqual(chrome.translate_url("/de/personen", "en"), "/en/people")
		self.assertEqual(chrome.translate_url("/de/implementierungen/fertigung-2023", "en"),
			"/en/implementations/fertigung-2023")
		self.assertEqual(chrome.translate_url("/en/industries", "de"), "/de/branchen")

	def test_other_urls_are_left_alone(self):
		self.assertEqual(chrome.translate_url("/de/personen", "de"), "/de/personen")  # already in that language
		for url in ("/blog", "https://example.com/de/personen", "/de/unbekannt", "", None):
			self.assertEqual(chrome.translate_url(url, "en"), url)

	def test_translated_web_page_url_is_swapped(self):
		if not frappe.get_meta("Web Page").has_field("translation_of"):
			self.skipTest("Web Page custom fields missing: run bench migrate")
		german = frappe.get_doc({"doctype": "Web Page", "title": "WP Test Preise", "route": "de/wp-test-preise",
			"language": "de", "published": 1}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "Web Page", "title": "WP Test Pricing", "route": "en/wp-test-pricing",
			"language": "en", "translation_of": german.name, "published": 1}).insert(ignore_permissions=True)
		self.assertEqual(chrome.translate_url("/de/wp-test-preise", "en"), "/en/wp-test-pricing")
		self.assertEqual(chrome.translate_url("/en/wp-test-pricing", "de"), "/de/wp-test-preise")

	def test_navbar_links_follow_the_page_language_without_touching_settings(self):
		item = frappe._dict(label="People", url="/de/personen", child_items=[frappe._dict(label="Teams", url="/de/teams")])
		context = frappe._dict(section_config={"slugs": {}}, lang="en", top_bar_items=[item], footer_items=[])
		values = chrome.update_website_context(context)
		self.assertEqual(values["wp_lang"], "en")
		self.assertEqual(values["top_bar_items"][0].url, "/en/people")
		self.assertEqual(values["top_bar_items"][0].child_items[0].url, "/en/teams")
		self.assertEqual(item.url, "/de/personen")  # cached Website Settings rows stay German

	# --- DIN 5008 footer ---------------------------------------------------------------------------

	def test_company_footer_never_shows_the_full_iban(self):
		footer = chrome.company_footer()
		if not footer.get("bank"):
			self.skipTest("no company bank account on this site")
		self.assertIn("*", footer.bank.iban)
