# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Public documentation pages under /de/doku (phamos/phamos#2005).

Pages are rendered as a crawler gets them: as Guest, from the content the BookStack sync copied.
Run with
    bench --site <site> run-tests --module phamos.tests.test_web_docs
"""

import json
import re

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import set_request
from frappe.website.serve import get_response_content

from phamos.web_profile import docs

INSTANCE = "BS Docs Test"


def _render(path):
	frappe.set_user("Guest")
	set_request(method="GET", path=path)
	try:
		return get_response_content(path)
	finally:
		frappe.set_user("Administrator")


def _jsonld(html):
	blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
	return [entry for block in blocks for entry in json.loads(block)]


def _is_404(html):
	return "is_404 = true" in html


class TestWebDocs(FrappeTestCase):
	def setUp(self):
		frappe.db.savepoint("web_docs_test")
		frappe.get_doc({
			"doctype": "Bookstack Configuration", "title": INSTANCE, "enabled": 1,
			"instance_url": "https://doku.example.test", "token_id": "id", "token_secret": "secret",
		}).insert(ignore_permissions=True)
		self.book = self._insert("Bookstack Book", 1, title="Handbuch & Test", slug="handbuch-test",
			publish_on_website=1, website_summary="Alles über Konten & Steuern.",
			url="https://doku.example.test/books/handbuch-test")
		self.hidden = self._insert("Bookstack Book", 2, title="Intern", slug="intern-test")
		chapter = self._insert("Bookstack Chapter", 10, title="Grundlagen", slug="grundlagen",
			book=self.book, priority=2)
		self._insert("Bookstack Page", 100, title="Erste Schritte", slug="erste-schritte", book=self.book,
			priority=1, html="<p>Willkommen im Handbuch. <strong>Los geht's.</strong></p>")
		self._insert("Bookstack Page", 101, title="Konten", slug="konten", book=self.book, chapter=chapter,
			priority=1, html="<h2>Konten</h2><table><tr><td>1200</td></tr></table>")
		self._insert("Bookstack Page", 102, title="Entwurf", slug="entwurf", book=self.book, priority=3)
		self._insert("Bookstack Page", 200, title="Geheim", slug="geheim", book=self.hidden,
			html="<p>Geheim</p>")
		docs.clear_cache()

	def tearDown(self):
		frappe.db.rollback(save_point="web_docs_test")
		docs.clear_cache()

	def _insert(self, doctype, bookstack_id, **values):
		doc = frappe.get_doc({"doctype": doctype, "instance": INSTANCE, "bookstack_id": bookstack_id, **values})
		doc.insert(ignore_permissions=True)
		return doc.name

	def test_overview_lists_published_books_only(self):
		html = _render("de/doku")

		self.assertIn('href="/de/doku/handbuch-test"', html)
		self.assertIn("Handbuch &amp; Test", html, "titles are escaped")
		self.assertNotIn("Handbuch & Test", html)
		self.assertNotIn("intern-test", html)
		self.assertIn("2 Seiten", html, "only pages with content are counted")

	def test_book_page_shows_contents_in_order(self):
		html = _render("de/doku/handbuch-test")

		first = html.index('href="/de/doku/handbuch-test/erste-schritte"')
		chapter = html.index('id="grundlagen"')
		second = html.index('href="/de/doku/handbuch-test/konten"')
		self.assertLess(first, chapter)
		self.assertLess(chapter, second)
		self.assertNotIn("entwurf", html, "pages without copied content are not listed")
		self.assertIn("Alles über Konten &amp; Steuern.", html)

	def test_page_shows_content_navigation_and_breadcrumbs(self):
		html = _render("de/doku/handbuch-test/konten")

		self.assertIn("<td>1200</td>", html)
		self.assertIn('rel="prev"', html)
		self.assertIn('href="/de/doku/handbuch-test/erste-schritte" rel="prev"', html)
		self.assertNotIn('rel="next"', html, "last page has no next")
		self.assertIn('aria-current="page">Konten', html)
		self.assertIn('<link rel="canonical" href="', html)
		self.assertIn('/de/doku/handbuch-test/konten"', html)
		self.assertNotIn('hreflang="en"', html, "German only")
		crumbs = next(e for e in _jsonld(html) if e["@type"] == "BreadcrumbList")
		self.assertEqual([c["name"] for c in crumbs["itemListElement"]],
			["Startseite", "Dokumentation", "Handbuch & Test", "Konten"])

	def test_description_comes_from_the_page_text(self):
		html = _render("de/doku/handbuch-test/konten")
		self.assertIn('<meta name="description" content="Konten 1200">', html)

	def test_unpublished_missing_or_empty_pages_are_not_found(self):
		for path in ("de/doku/intern-test", "de/doku/intern-test/geheim", "de/doku/nichts",
				"de/doku/handbuch-test/entwurf", "de/doku/handbuch-test/nichts", "doku", "doku/book"):
			self.assertTrue(_is_404(_render(path)), path)

	def test_unpublishing_takes_the_book_offline_at_once(self):
		self.assertFalse(_is_404(_render("de/doku/handbuch-test")))
		book = frappe.get_doc("Bookstack Book", self.book)
		book.publish_on_website = 0
		book.save(ignore_permissions=True)
		frappe.db.after_commit.run()  # what a commit does; the tests never commit
		self.assertTrue(_is_404(_render("de/doku/handbuch-test")))

	def test_pages_only_under_their_route(self):
		for path in ("doku?lang=de", "doku/index?lang=de", "doku/book?lang=de&book_slug=handbuch-test"):
			self.assertTrue(_is_404(_render(path)), path)

	def test_sync_may_save_a_published_book_whose_address_clashes(self):
		frappe.db.set_value("Bookstack Book", self.hidden, {"publish_on_website": 1, "slug": "intern-test"})
		book = frappe.get_doc("Bookstack Book", self.hidden)
		book.slug = "handbuch-test"  # renamed in BookStack into a clash
		book.save(ignore_permissions=True)  # what the sync does: no error

		other = frappe.get_doc("Bookstack Book", self.hidden)
		other.publish_on_website = 0
		other.save(ignore_permissions=True)
		other.publish_on_website = 1
		self.assertRaises(frappe.ValidationError, other.save, ignore_permissions=True)

	def test_footer_heading_lists_the_books(self):
		from phamos.web_profile.chrome import _footer_items

		items = _footer_items([frappe._dict(label="Dokumentation")], "de")
		links = [(c.label, c.url) for c in items[0].child_items]
		# The site may publish real books too; only this test's books are checked.
		self.assertIn(("Handbuch &amp; Test", "/de/doku/handbuch-test"), links)  # escaped for the footer
		self.assertNotIn("/de/doku/intern-test", [url for _, url in links])

	def test_book_titles_in_the_footer_are_escaped(self):
		from phamos.web_profile.chrome import _footer_items

		# Frappe stores "<" of a Data field escaped already; a raw one must still come out escaped.
		frappe.db.set_value("Bookstack Book", self.book, "title", "<img src=x onerror=alert(1)>")
		docs.clear_cache()
		items = _footer_items([frappe._dict(label="Dokumentation")], "de")
		labels = [c.label for c in items[0].child_items]
		self.assertIn("&lt;img src=x onerror=alert(1)&gt;", labels)
		self.assertNotIn("<img", " ".join(labels))

	def test_two_published_books_cannot_share_a_web_address(self):
		other = frappe.get_doc({"doctype": "Bookstack Book", "instance": INSTANCE, "bookstack_id": 3,
			"title": "Kopie", "slug": "handbuch-test"}).insert(ignore_permissions=True)
		other.publish_on_website = 1
		self.assertRaises(frappe.ValidationError, other.save, ignore_permissions=True)


MODULE = "WP Docs Test Module"


class TestModuleDocumentationLinks(TestWebDocs):
	"""Module pages link their books, the book page links back (phamos/phamos#2006)."""

	def setUp(self):
		super().setUp()
		from phamos.web_profile.sections import clear_items

		if not frappe.db.exists("Implementation Module", MODULE):
			frappe.get_doc({"doctype": "Implementation Module", "module_name": MODULE}).insert(ignore_permissions=True)
		self.profile = frappe.get_doc({
			"doctype": "Module Web Profile", "module": MODULE, "published": 1, "route": "docs-test-modul",
			"documentation": [{"book": self.book}, {"book": self.hidden}],
		}).insert(ignore_permissions=True)
		clear_items()

	def tearDown(self):
		super().tearDown()
		from phamos.web_profile.sections import clear_items

		clear_items()

	def test_module_page_shows_published_books(self):
		html = _render("de/module/docs-test-modul")

		self.assertIn("Dokumentation", html)
		self.assertIn('href="/de/doku/handbuch-test"', html)
		self.assertNotIn("intern-test", html, "unpublished books are left out")
		self.assertNotIn("auf Deutsch", html)

	def test_english_module_page_says_the_books_are_german(self):
		html = _render("en/modules/docs-test-modul")

		self.assertIn('href="/de/doku/handbuch-test"', html)
		self.assertIn("in German", html)

	def test_unpublishing_removes_the_tile(self):
		book = frappe.get_doc("Bookstack Book", self.book)
		book.publish_on_website = 0
		book.save(ignore_permissions=True)

		self.assertNotIn('href="/de/doku/handbuch-test"', _render("de/module/docs-test-modul"))

	def test_book_page_links_back_to_the_module(self):
		html = _render("de/doku/handbuch-test")

		self.assertIn("Passendes Modul", html)
		self.assertIn('href="/de/module/docs-test-modul"', html)

	def test_deleted_book_leaves_no_module_link_behind(self):
		frappe.delete_doc("Bookstack Book", self.hidden, ignore_permissions=True, force=True)
		self.assertFalse(frappe.db.exists("Web Profile Book", {"book": self.hidden}))
		self.profile.reload()
		self.profile.save(ignore_permissions=True)  # failed with "Could not find Bookstack Book" before
		self.assertEqual([r.book for r in self.profile.documentation], [self.book])

	def test_deleting_a_book_clears_the_module_items_after_the_commit(self):
		from phamos.web_profile.sections import get_items

		get_items("modules", "de")  # fills the request copy and the Redis cache
		frappe.delete_doc("Bookstack Book", self.hidden, ignore_permissions=True, force=True)
		frappe.db.after_commit.run()  # what a commit does; the tests never commit
		self.assertIsNone(frappe.local.web_profile_items, "the request copy is cleared too")
		self.assertIsNone(frappe.cache.hget("web_profile_items", "modules:de"))
