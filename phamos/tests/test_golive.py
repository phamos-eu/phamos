# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Go-live of a website section by data: redirects, unpublishing, rollback (phamos/phamos#1492 step 5).

Run with
    bench --site <site> run-tests --module phamos.tests.test_golive
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.web_profile import golive
from phamos.web_profile.sections import get_items


def _redirects():
	return {golive._path(r.source): r.target for r in frappe.get_single("Website Settings").route_redirects}


class TestGolive(FrappeTestCase):
	def setUp(self):
		frappe.local.lang = "en"
		frappe.db.savepoint("golive_test")
		self.page = self._page("people/wp-golive-test", "WP Golive Test", published=1)
		self.old = self._page("people/wp-golive-old", "WP Golive Old", published=0)

	def tearDown(self):
		frappe.db.rollback(save_point="golive_test")
		frappe.cache.delete_key("website_redirects")

	def _page(self, route, title, published):
		return frappe.get_doc({"doctype": "Web Page", "title": title, "route": route,
			"published": published}).insert(ignore_permissions=True).name

	def test_dry_run_changes_nothing(self):
		before = _redirects()
		report = golive.run("people", verbose=0)
		self.assertIn(("people/wp-golive-test", "/de/personen"), report.added)
		self.assertEqual(_redirects(), before)
		self.assertEqual(frappe.db.get_value("Web Page", self.page, "published"), 1)

	def test_run_redirects_and_unpublishes_and_a_second_run_changes_nothing(self):
		golive.run("people", dry_run=0, verbose=0)
		self.assertEqual(_redirects().get("people/wp-golive-test"), "/de/personen")
		self.assertEqual(frappe.db.get_value("Web Page", self.page, "published"), 0)
		again = golive.run("people", dry_run=0, verbose=0)
		self.assertFalse(again.added)
		self.assertIn(("people/wp-golive-test", "/de/personen"), again.unchanged)

	def test_old_url_is_matched_literally(self):
		golive.run("people", dry_run=0, verbose=0)
		row = next(r for r in frappe.get_single("Website Settings").route_redirects
			if golive._path(r.source) == "people/wp-golive-test")
		self.assertEqual(row.source, "people/wp\\-golive\\-test")  # "-" escaped: Frappe reads a regex

	def test_rollback_restores_only_what_the_run_changed(self):
		golive.run("people", dry_run=0, verbose=0)
		golive.rollback("people", dry_run=0, verbose=0)
		self.assertNotIn("people/wp-golive-test", _redirects())
		self.assertEqual(frappe.db.get_value("Web Page", self.page, "published"), 1)
		# Unpublished before the go-live, so it stays unpublished.
		self.assertEqual(frappe.db.get_value("Web Page", self.old, "published"), 0)

	def test_a_differently_configured_old_url_is_left_alone(self):
		settings = frappe.get_single("Website Settings")
		settings.append("route_redirects", {"source": "people/wp-golive-test", "target": "/elsewhere"})
		settings.save(ignore_permissions=True)
		report = golive.run("people", dry_run=0, verbose=0)
		self.assertIn(("people/wp-golive-test", "/elsewhere", "/de/personen"), report.conflicts)
		self.assertEqual(_redirects()["people/wp-golive-test"], "/elsewhere")

	def test_old_urls_never_lead_to_anonymous_profiles(self):
		masked = {f"/de/personen/{i.slug}" for i in get_items("people", "de") if i.masked}
		targets = {target for _source, target in golive.get_plan("people").redirects}
		self.assertFalse(masked & targets)

	def test_unknown_section_is_refused(self):
		self.assertRaises(frappe.ValidationError, golive.get_plan, "no_such_section")
		self.assertRaises(frappe.ValidationError, golive.get_plan, "../hooks")
