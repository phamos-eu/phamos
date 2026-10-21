# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The content Web Pages stay editable in the Desk (phamos/phamos#1539).

Content lives in the database only: no code writes it, an edit shows on the page, the go-live run and
the one-time conversion (phamos.web_profile.page_builder) never overwrite it.

Run with
    bench --site <site> run-tests --module phamos.tests.test_web_page_editing
"""

import os

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response_content

from phamos.web_profile import golive, page_builder

CONTENT_FIELDS = ("content_type", "main_section", "main_section_md", "main_section_html")

HERO = ('<section class="section section-padding-top" data-section-template="Hero"><div class="container">'
	'<div class="hero align-center"><div class="hero-content"><h1 class="hero-title">WP Test Leistungen</h1>'
	'<p class="hero-subtitle">Wir <b>helfen</b> gern.</p><div class="hero-buttons">'
	'<a class="btn btn-lg btn-dark" href="/de/kontakt">Kontakt</a></div></div></div></div></section>')
CONTACT = ('<section class="section"><div class="container"><p>Schreiben Sie uns.</p><button type="button" '
	'class="wp-button wp-button-primary" data-wp-contact-open data-section="contact" data-slug="general">'
	'Nachricht senden</button></div></section>')


class TestWebPageEditing(FrappeTestCase):
	def setUp(self):
		if not frappe.get_meta("Web Page").has_field("translation_of"):
			self.skipTest("Web Page custom fields missing: run bench migrate")
		if not frappe.db.exists("Web Template", page_builder.CONTACT_TEMPLATE):
			self.skipTest("Web Template 'phamos Contact Button' missing: run bench migrate")
		frappe.db.savepoint("web_page_editing_test")

	def tearDown(self):
		frappe.db.rollback(save_point="web_page_editing_test")
		frappe.set_user("Administrator")

	def _page(self, route, **fields):
		return frappe.get_doc({"doctype": "Web Page", "title": route, "route": route, "published": 1,
			"language": route.split("/")[0], **fields}).insert(ignore_permissions=True, set_name=route.replace("/", "-"))

	def _render(self, route):
		frappe.set_user("Guest")
		set_request(method="GET", path=route)
		try:
			return get_response_content(route)
		finally:
			frappe.set_user("Administrator")

	# --- content lives in the database only -------------------------------------------------------------

	def test_the_app_ships_no_web_pages(self):
		# A web_page folder in a module is synced on every migrate and would overwrite Desk edits.
		app = frappe.get_app_path("phamos")
		folders = [root for root, dirs, _ in os.walk(app) if os.path.basename(root) == "web_page"
			and "node_modules" not in root]
		self.assertEqual(folders, [])
		fixtures = [f if isinstance(f, str) else f.get("dt") for f in frappe.get_hooks("fixtures", app_name="phamos")]
		self.assertNotIn("Web Page", fixtures)

	def test_every_edit_is_a_version(self):
		self.assertTrue(frappe.get_meta("Web Page").track_changes)

	# --- an edit shows on the page ---------------------------------------------------------------------

	def test_an_edited_block_shows_on_the_page(self):
		page = self._page("de/wp-test-bloecke", content_type="Page Builder", page_blocks=[{"web_template": "Hero",
			"web_template_values": frappe.as_json({"title": "Erste Fassung"})}])
		self.assertIn("Erste Fassung", self._render(page.route))

		page.page_blocks[0].web_template_values = frappe.as_json({"title": "Zweite Fassung"})
		page.save(ignore_permissions=True)
		html = self._render(page.route)
		self.assertIn("Zweite Fassung", html)
		self.assertNotIn("Erste Fassung", html)

	def test_content_pages_name_themselves_for_the_edit_link(self):
		page = self._page("de/wp-test-bearbeiten", content_type="Rich Text", main_section="<p>Text</p>")
		html = self._render(page.route)
		self.assertIn(f'<meta name="wp-web-page" content="{page.name}"', html)
		self.assertNotIn("/app/web-page", html)  # the page is cached for everyone: the link is added in the browser

	# --- conversion of the old HTML pages --------------------------------------------------------------

	def test_html_page_becomes_blocks_with_its_text_links_and_contact_button(self):
		page = self._page("de/wp-test-leistungen", content_type="HTML", main_section_html=HERO + CONTACT)
		page_builder.convert(dry_run=0, pages=[page.name], verbose=0)
		page.reload()
		self.assertEqual(page.content_type, "Page Builder")
		self.assertEqual([b.web_template for b in page.page_blocks], ["Hero", page_builder.CONTACT_TEMPLATE])
		hero = frappe.parse_json(page.page_blocks[0].web_template_values)
		self.assertEqual((hero.title, hero.primary_action, hero.align), ("WP Test Leistungen", "/de/kontakt", "Center"))
		self.assertTrue(page.page_blocks[0].add_top_padding)
		self.assertFalse(page.page_blocks[0].add_bottom_padding)

		html = self._render(page.route)
		for text in ("WP Test Leistungen", "helfen", 'href="/de/kontakt"', "Schreiben Sie uns.", "data-wp-contact-open",
			"Nachricht senden"):
			self.assertIn(text, html)

	def test_legal_page_becomes_rich_text(self):
		html = '<div class="webpage-content"><article><div class="ql-editor read-mode"><h1>Impressum</h1><p>phamos GmbH</p></div></article></div>'
		page = self._page("de/wp-test/impressum", content_type="HTML", main_section_html=html)
		page_builder.convert(dry_run=0, pages=[page.name], verbose=0)
		page.reload()
		self.assertEqual((page.content_type, page.main_section), ("Rich Text", "<h1>Impressum</h1><p>phamos GmbH</p>"))

	def test_conversion_never_touches_a_page_edited_in_the_desk(self):
		page = self._page("de/wp-test-zweimal", content_type="HTML", main_section_html=HERO)
		page_builder.convert(dry_run=0, pages=[page.name], verbose=0)
		page.reload()
		page.page_blocks[0].web_template_values = frappe.as_json({"title": "Im Desk geändert"})
		page.save(ignore_permissions=True)

		page_builder.convert(dry_run=0, pages=[page.name], verbose=0)
		page.reload()
		self.assertEqual(frappe.parse_json(page.page_blocks[0].web_template_values).title, "Im Desk geändert")

	def test_rollback_shows_the_old_html_again(self):
		page = self._page("de/wp-test-zurueck", content_type="HTML", main_section_html=HERO)
		page_builder.convert(dry_run=0, pages=[page.name], verbose=0)
		page_builder.rollback(dry_run=0, pages=[page.name], verbose=0)
		page.reload()
		self.assertEqual((page.content_type, page.main_section_html), ("HTML", HERO))

	def test_dry_run_changes_nothing(self):
		page = self._page("de/wp-test-probe", content_type="HTML", main_section_html=HERO)
		page_builder.convert(pages=[page.name], verbose=0)
		self.assertEqual(frappe.db.get_value("Web Page", page.name, "content_type"), "HTML")

	# --- go-live --------------------------------------------------------------------------------------

	def test_golive_twice_leaves_the_content_alone(self):
		german = self._page("de/wp-test-preise", content_type="Page Builder", page_blocks=[{"web_template": "Hero",
			"web_template_values": frappe.as_json({"title": "Preise"})}])
		english = self._page("en/wp-test-pricing", translation_of=german.name, content_type="Rich Text",
			main_section="<p>Pricing</p>")
		before = {p.name: tuple(frappe.db.get_value("Web Page", p.name, CONTENT_FIELDS)) for p in (german, english)}
		blocks = german.page_blocks[0].web_template_values

		for _ in range(2):
			golive.run("content", dry_run=0, verbose=0)
		for name, values in before.items():
			self.assertEqual(tuple(frappe.db.get_value("Web Page", name, CONTENT_FIELDS)), values)
		self.assertEqual(frappe.get_doc("Web Page", german.name).page_blocks[0].web_template_values, blocks)
