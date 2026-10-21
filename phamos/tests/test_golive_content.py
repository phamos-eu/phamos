# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Go-live plan of the content pages (phamos/phamos#1539, step 5i of #1492).

Run with
    bench --site <site> run-tests --module phamos.tests.test_golive_content
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.web_profile import golive


class TestGoliveContent(FrappeTestCase):
	def setUp(self):
		if not frappe.get_meta("Web Page").has_field("translation_of"):
			self.skipTest("Web Page custom fields missing: run bench migrate")
		frappe.db.savepoint("golive_content_test")
		self.german = self._page("de/wp-test-preise", "WP Test Preise", language="de")
		self._page("en/wp-test-pricing", "WP Test Pricing", language="en", translation_of=self.german)
		self.legacy = self._page("wp-test-pricing-old", "WP Test Pricing")

	def tearDown(self):
		frappe.db.rollback(save_point="golive_content_test")

	def _page(self, route, title, **fields):
		# Web Pages are named after their title; the old and the new page share one here.
		return frappe.get_doc({"doctype": "Web Page", "title": title, "route": route, "published": 1,
			**fields}).insert(ignore_permissions=True, set_name=route.replace("/", "-")).name

	def test_old_urls_without_a_language_lead_to_the_german_page(self):
		redirects = dict(golive.get_plan("content").redirects)
		self.assertEqual(redirects["wp-test-preise"], "/de/wp-test-preise")
		self.assertEqual(redirects["wp-test-pricing"], "/de/wp-test-preise")

	def test_an_old_page_with_a_translated_counterpart_is_unpublished(self):
		plan = golive.get_plan("content")
		self.assertEqual(dict(plan.redirects)["wp-test-pricing-old"], "/de/wp-test-preise")
		self.assertIn(self.legacy, plan.unpublish)

	def test_section_pages_are_left_to_their_own_plans(self):
		self._page("people/wp-test-person", "WP Test Pricing")
		self.assertNotIn("people/wp-test-person", dict(golive.get_plan("content").redirects))
