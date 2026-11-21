# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Public documentation pages under /de/dokumentation and /en/documentation (phamos/phamos#2005, #2044).

Pages are rendered as a crawler gets them: as Guest, from the content the BookStack sync copied.
Run with
    bench --site <site> run-tests --module phamos.tests.test_web_docs
"""

import json
import re

from unittest.mock import patch

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


class DocsFixture(FrappeTestCase):
	"""Published book with a chapter, an unpublished book; no tests of its own."""

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


class TestWebDocs(DocsFixture):
	def test_overview_lists_published_books_only(self):
		html = _render("de/dokumentation")

		self.assertIn('href="/de/dokumentation/handbuch-test"', html)
		self.assertIn("Handbuch &amp; Test", html, "titles are escaped")
		self.assertNotIn("Handbuch & Test", html)
		self.assertNotIn("intern-test", html)
		self.assertIn("2 Seiten", html, "only pages with content are counted")

	def test_book_page_shows_contents_in_order(self):
		html = _render("de/dokumentation/handbuch-test")

		first = html.index('href="/de/dokumentation/handbuch-test/erste-schritte"')
		chapter = html.index('id="grundlagen"')
		second = html.index('href="/de/dokumentation/handbuch-test/konten"')
		self.assertLess(first, chapter)
		self.assertLess(chapter, second)
		self.assertNotIn("entwurf", html, "pages without copied content are not listed")
		self.assertIn("Alles über Konten &amp; Steuern.", html)

	def test_page_shows_content_navigation_and_breadcrumbs(self):
		html = _render("de/dokumentation/handbuch-test/konten")

		self.assertIn("<td>1200</td>", html)
		# wide tables scroll in a box of their own, with the cockpit's scroll hint (#2045)
		self.assertRegex(html, r'<div class="wp-docs-table" data-wp-docs-table=""><div class="wp-docs-table-scroll"><table>')
		self.assertIn('data-label-more-right="Mehr rechts"', html)
		self.assertIn('rel="prev"', html)
		self.assertIn('href="/de/dokumentation/handbuch-test/erste-schritte" rel="prev"', html)
		self.assertNotIn('rel="next"', html, "last page has no next")
		self.assertIn('aria-current="page">Konten', html)
		self.assertRegex(html, r'<link rel="canonical" href="[^"]*/de/dokumentation/handbuch-test/konten">')
		self.assertRegex(html, r'hreflang="en" href="[^"]*/en/documentation/handbuch-test/konten"')
		crumbs = next(e for e in _jsonld(html) if e["@type"] == "BreadcrumbList")
		self.assertEqual([c["name"] for c in crumbs["itemListElement"]],
			["Startseite", "Dokumentation", "Handbuch & Test", "Konten"])

	def test_description_comes_from_the_page_text(self):
		html = _render("de/dokumentation/handbuch-test/konten")
		self.assertIn('<meta name="description" content="Konten 1200">', html)

	def test_unpublished_missing_or_empty_pages_are_not_found(self):
		for path in ("de/dokumentation/intern-test", "de/dokumentation/intern-test/geheim", "de/dokumentation/nichts",
				"de/dokumentation/handbuch-test/entwurf", "de/dokumentation/handbuch-test/nichts", "documentation",
				"documentation/book", "de/doku", "de/doku/handbuch-test", "en/dokumentation", "de/documentation"):
			self.assertTrue(_is_404(_render(path)), path)

	def test_unpublishing_takes_the_book_offline_at_once(self):
		self.assertFalse(_is_404(_render("de/dokumentation/handbuch-test")))
		book = frappe.get_doc("Bookstack Book", self.book)
		book.publish_on_website = 0
		book.save(ignore_permissions=True)
		frappe.db.after_commit.run()  # what a commit does; the tests never commit
		self.assertTrue(_is_404(_render("de/dokumentation/handbuch-test")))

	def test_pages_only_under_their_route(self):
		for path in ("documentation?lang=de", "documentation/index?lang=de",
				"documentation/book?lang=de&book_slug=handbuch-test", "documentation?lang=en"):
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
		self.assertIn(("Handbuch &amp; Test", "/de/dokumentation/handbuch-test"), links)  # escaped for the footer
		self.assertNotIn("/de/dokumentation/intern-test", [url for _, url in links])

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


class TestModuleDocumentationLinks(DocsFixture):
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
		self.assertIn('href="/de/dokumentation/handbuch-test"', html)
		self.assertNotIn("intern-test", html, "unpublished books are left out")
		self.assertNotIn("auf Deutsch", html)

	def test_english_module_page_says_the_books_are_german(self):
		html = _render("en/modules/docs-test-modul")

		self.assertIn('href="/en/documentation/handbuch-test"', html)
		self.assertIn("in German", html)

	def test_unpublishing_removes_the_tile(self):
		book = frappe.get_doc("Bookstack Book", self.book)
		book.publish_on_website = 0
		book.save(ignore_permissions=True)

		self.assertNotIn('href="/de/dokumentation/handbuch-test"', _render("de/module/docs-test-modul"))

	def test_book_page_links_back_to_the_module(self):
		html = _render("de/dokumentation/handbuch-test")

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


class TestDocsEnglishAndLinks(DocsFixture):
	"""English pages and links to the website pages (phamos/phamos#2044)."""

	def setUp(self):
		super().setUp()
		# An older, unpublished copy of the book, as on doku.phamos.eu (v13, v15 ...).
		self.old = self._insert("Bookstack Book", 33, title="Handbuch v13", slug="handbuch-test-v13")
		self._insert("Bookstack Page", 330, title="Konten (alt)", slug="konten", book=self.old)
		self._insert("Bookstack Page", 331, title="Konten", slug="konten-uebersicht", book=self.old)  # other slug
		base = "https://doku.example.test"
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-100", "html", (
			f'<p><a href="{base}/books/handbuch-test/page/konten#bkmrk-x">eigen</a>'
			f'<a href="{base}/books/handbuch-test-v13/page/konten">alt</a>'
			f'<a href="{base}/link/330">permalink alt</a>'
			f'<a href="{base}/books/handbuch-test-v13/chapter/grundlagen">kapitel alt</a>'
			f'<a href="{base}/books/handbuch-test-v13">buch alt</a>'
			f'<a href="{base}/books/handbuch-test-v13/page/nur-alt">fehlt</a>'
			f'<a href="{base}/books/intern-test/page/geheim">intern</a>'
			f'<a href="{base}/books/handbuch-test-v13/page/konten-uebersicht">titel</a>'
			f'<a href="{base}/books/handbuch-test/chapter/:~:text=4%20Seiten">kaputt</a>'
			f'<a href="https://frappe.io" rel="noopener">extern</a></p>'))
		docs.clear_cache()

	def test_english_route_shows_the_german_text_with_english_navigation(self):
		html = _render("en/documentation/handbuch-test/konten")

		self.assertIn("<td>1200</td>", html)
		self.assertIn("This documentation is in German.", html)
		self.assertIn('lang="de"', html)
		self.assertRegex(html, r'<link rel="canonical" href="[^"]*/de/dokumentation/handbuch-test/konten">')
		self.assertIn('href="/en/documentation/handbuch-test/erste-schritte" rel="prev"', html)
		crumbs = next(e for e in _jsonld(html) if e["@type"] == "BreadcrumbList")
		self.assertEqual([c["name"] for c in crumbs["itemListElement"]][:2], ["Home", "Documentation"])

	def test_english_overview_and_book(self):
		self.assertIn('href="/en/documentation/handbuch-test"', _render("en/documentation"))
		self.assertIn('href="/en/documentation/handbuch-test/konten"', _render("en/documentation/handbuch-test"))

	def test_language_switch_maps_the_routes(self):
		from phamos.web_profile.chrome import translate_url

		self.assertEqual(translate_url("/de/dokumentation/handbuch-test/konten", "en"), "/en/documentation/handbuch-test/konten")
		self.assertEqual(translate_url("/en/documentation", "de"), "/de/dokumentation")

	def test_links_point_to_the_website_matched_by_slug(self):
		html = _render("de/dokumentation/handbuch-test/erste-schritte")
		base = "https://doku.example.test"

		self.assertIn('href="/de/dokumentation/handbuch-test/konten#bkmrk-x">eigen', html)
		self.assertIn('href="/de/dokumentation/handbuch-test/konten">alt', html, "older copy, same page slug")
		self.assertIn('href="/de/dokumentation/handbuch-test/konten">permalink alt', html, "permalink to the older copy")
		self.assertIn('href="/de/dokumentation/handbuch-test#grundlagen">kapitel alt', html)
		self.assertIn('href="/de/dokumentation/handbuch-test">buch alt', html, "same book family")
		self.assertIn(f'href="{base}/books/handbuch-test-v13/page/nur-alt"', html, "no match: stays on BookStack")
		self.assertIn(f'href="{base}/books/intern-test/page/geheim"', html, "unpublished, no match")
		self.assertIn('href="https://frappe.io" rel="noopener"', html)
		self.assertIn('href="/de/dokumentation/handbuch-test/konten">titel', html, "other slug, same title")
		self.assertIn('href="/de/dokumentation/handbuch-test">kaputt', html, "broken chapter link opens the book")

	def test_permalink_ids_belong_to_their_instance(self):
		from phamos.web_profile.docs import link_index, website_href

		index = link_index()
		self.assertEqual(website_href("https://doku.example.test/link/330", index), "/de/dokumentation/handbuch-test/konten")
		self.assertIsNone(website_href("https://andere-doku.example.test/link/330", index), "another host's page 330")

	def test_english_page_links_stay_english(self):
		html = _render("en/documentation/handbuch-test/erste-schritte")
		self.assertIn('href="/en/documentation/handbuch-test/konten">alt', html)

	def test_publishing_a_book_changes_links_without_a_sync(self):
		base = "https://doku.example.test"
		self.assertIn(f'href="{base}/books/intern-test/page/geheim"', _render("de/dokumentation/handbuch-test/erste-schritte"))

		book = frappe.get_doc("Bookstack Book", self.hidden)
		book.publish_on_website = 1
		book.save(ignore_permissions=True)
		frappe.db.after_commit.run()

		self.assertIn('href="/de/dokumentation/intern-test/geheim">intern', _render("de/dokumentation/handbuch-test/erste-schritte"))

	def test_old_copies_get_their_bookstack_links_back(self):
		from phamos.patches.v1_0.docs_links_back_to_bookstack import execute

		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-100", "html",
			'<a href="/de/doku/handbuch-test/konten#bkmrk-a">p</a><a href="/de/doku/handbuch-test#grundlagen">c</a>'
			'<a href="/de/doku/handbuch-test">b</a>')
		execute()
		html = frappe.db.get_value("Bookstack Page", f"{INSTANCE}-BSP-100", "html")
		base = "https://doku.example.test"
		self.assertEqual(html, f'<a href="{base}/books/handbuch-test/page/konten#bkmrk-a">p</a>'
			f'<a href="{base}/books/handbuch-test/chapter/grundlagen">c</a><a href="{base}/books/handbuch-test">b</a>')


class TestDocsLayout(DocsFixture):
	"""Full-width layouts, collapsible contents, "On this page", jump buttons (phamos/phamos#2045)."""

	def setUp(self):
		super().setUp()
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-101", "html",
			'<h2 id="bkmrk-a">Erster Teil</h2><p>a</p><h3>Unterpunkt</h3><p>b</p><h2>Zweiter Teil</h2>')
		docs.clear_cache()

	def test_page_lists_its_headings_and_gives_each_an_id(self):
		html = _render("de/dokumentation/handbuch-test/konten")

		self.assertIn("Auf dieser Seite", html)
		self.assertIn('href="#bkmrk-a" data-wp-docs-onpage="bkmrk-a">Erster Teil', html)
		self.assertRegex(html, r'<h3 id="(wp-h-\d+)">Unterpunkt</h3>')
		heading_id = re.search(r'<h3 id="(wp-h-\d+)">Unterpunkt', html).group(1)
		self.assertIn(f'href="#{heading_id}" data-wp-docs-onpage="{heading_id}">Unterpunkt', html)
		self.assertIn('class="wp-docs-onpage-h3"', html)

	def test_page_without_headings_has_no_on_this_page(self):
		self.assertNotIn("Auf dieser Seite", _render("de/dokumentation/handbuch-test/erste-schritte"))

	def test_contents_open_the_current_chapter_and_can_be_hidden(self):
		html = _render("de/dokumentation/handbuch-test/konten")

		self.assertRegex(html, r'<details open>\s*<summary>Grundlagen</summary>')
		self.assertIn("data-wp-docs-nav-toggle hidden", html, "the button appears with the script")
		self.assertIn('data-label-hide="Inhalt ausblenden"', html)
		self.assertRegex(html, r'<script[^>]+src="[^"]*web_docs\.bundle')
		self.assertIn('data-wp-docs-next="h2, h3"', html)

	def test_book_shows_numbered_folding_chapters(self):
		html = _render("de/dokumentation/handbuch-test")

		self.assertRegex(html, r'<details class="wp-docs-chapter" id="grundlagen" data-wp-docs-chapter>')
		self.assertIn('<span class="wp-docs-chapter-num" aria-hidden="true">1</span>', html)
		self.assertIn("1 Seite", html)
		self.assertNotIn("Lesen beginnen", html)
		self.assertIn('data-wp-docs-next="[data-wp-docs-chapter]"', html)
		self.assertIn('class="wp-docs-loose"', html, "a page outside chapters stays in its place")

	def test_other_website_pages_do_not_load_the_docs_script(self):
		self.assertNotRegex(_render("de/module"), r'<script[^>]+src="[^"]*web_docs\.bundle')


class TestDocsSearch(DocsFixture):
	"""Search in published books and pages only (phamos/phamos#2046). The site may publish real books
	too, so results are checked within this test's books."""

	def setUp(self):
		super().setUp()
		from phamos.bookstack_integration.content import plain_text

		for name in frappe.get_all("Bookstack Page", filters={"instance": INSTANCE, "html": ["is", "set"]}, pluck="name"):
			html = frappe.db.get_value("Bookstack Page", name, "html")
			frappe.db.set_value("Bookstack Page", name, "search_text", plain_text(html))
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-100", {"html": "<p>Die Umsatzsteuer & mehr</p>",
			"search_text": "Die Umsatzsteuer & mehr wird am Xqzmonatsende gebucht"})
		docs.clear_cache()

	def _search(self, q, book_slug="handbuch-test"):
		from phamos.web_profile.docs_search import search

		return search(q, "de", book_slug=book_slug)

	def _render_query(self, path, **query):
		"""The results page as a visitor gets it: the query in the query string, not the path."""
		from urllib.parse import urlencode

		frappe.set_user("Guest")
		set_request(method="GET", path=path, query_string=urlencode(query))
		frappe.local.form_dict = frappe._dict(query)
		try:
			return get_response_content(path)
		finally:
			frappe.set_user("Administrator")

	def test_a_word_inside_the_text_finds_the_page(self):
		pages = self._search("Xqzmonatsende", book_slug=None)["pages"]
		self.assertEqual([p["title"] for p in pages], ["Erste Schritte"])
		self.assertIn("<mark>Xqzmonatsende</mark>", pages[0]["snippet"])

	def test_unpublished_books_never_appear(self):
		urls = [p["url"] for p in self._search("Geheim", book_slug=None)["pages"]]
		self.assertFalse([u for u in urls if "intern-test" in u])
		self.assertEqual(self._search("Geheim", book_slug="intern-test")["pages"], [])

	def test_all_words_must_match_and_titles_come_first(self):
		self.assertEqual(self._search("Umsatzsteuer nirgends")["pages"], [])
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-100", "search_text", "Hier geht es um Konten")
		titles = [p["title"] for p in self._search("Konten")["pages"]]
		self.assertEqual(titles, ["Konten", "Erste Schritte"])

	def test_snippet_is_escaped(self):
		self.assertIn("&amp;", self._search("Umsatzsteuer")["pages"][0]["snippet"])
		snippet = self._search("am Xqzmonatsende")["pages"][0]["snippet"]
		self.assertIn("&amp;", snippet, "a match never splits an entity")
		self.assertIn(" <mark>am</mark> ", snippet)

	def test_wildcards_are_literal(self):
		self.assertEqual(self._search("%%")["pages"], [])
		self.assertEqual(self._search("__")["pages"], [])

	def test_scope_by_book(self):
		self.assertEqual(len(self._search("Xqzmonatsende")["pages"]), 1)
		self.assertEqual(self._search("Xqzmonatsende", book_slug="intern-test")["pages"], [])

	def test_books_are_found_by_title(self):
		slugs = [b.slug for b in self._search("Handbuch", book_slug=None)["books"]]
		self.assertIn("handbuch-test", slugs)
		self.assertNotIn("intern-test", slugs)

	def test_results_page(self):
		html = self._render_query("de/dokumentation/suche", q="Xqzmonatsende")
		self.assertIn('href="/de/dokumentation/handbuch-test/erste-schritte"', html)
		self.assertIn("1 Treffer für „Xqzmonatsende“", html)
		self.assertIn('content="noindex, follow"', html)
		self.assertIn("Bitte mindestens 2 Zeichen", self._render_query("de/dokumentation/suche", q="a"))
		self.assertIn("Keine Treffer", self._render_query("de/dokumentation/suche", q="Nichtsdergleichenxq"))
		english = self._render_query("en/documentation/search", q="Xqzmonatsende")
		self.assertIn('href="/en/documentation/handbuch-test/erste-schritte"', english)
		scoped = self._render_query("de/dokumentation/suche", q="Xqzmonatsende", book="handbuch-test")
		self.assertIn("In allen Büchern suchen", scoped)

	def test_search_boxes_on_the_pages(self):
		self.assertIn('action="/de/dokumentation/suche"', _render("de/dokumentation"))
		self.assertIn('name="book" value="handbuch-test" checked', _render("de/dokumentation/handbuch-test"))
		self.assertIn('name="book" value="handbuch-test" checked', _render("de/dokumentation/handbuch-test/konten"))

	def test_suggestions_for_guests(self):
		from phamos.web_profile.docs_search import suggest

		frappe.local.request = None  # called directly, not over HTTP: no rate limit
		frappe.set_user("Guest")
		try:
			rows = suggest(q="Xqzmonatsende", lang="de")
			self.assertEqual(suggest(q="a"), [])
		finally:
			frappe.set_user("Administrator")
		self.assertEqual(rows[0]["url"], "/de/dokumentation/handbuch-test/erste-schritte")
		self.assertNotIn("snippet", rows[0])

	def test_suggestions_are_rate_limited(self):
		from phamos.web_profile import docs_search

		self.assertTrue(hasattr(docs_search.suggest, "__wrapped__"), "rate_limit wraps the method")

	def test_count_and_title_hits_do_not_depend_on_the_row_limit(self):
		from phamos.web_profile import docs_search

		# "Konten" gets the word in its title; "Erste Schritte" (alphabetically first) only in its text
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-101", "search_text", "Xqzmonatsende im Text")
		frappe.db.set_value("Bookstack Page", f"{INSTANCE}-BSP-101", "title", "Zum Xqzmonatsende")
		docs.clear_cache()
		with patch.object(docs_search, "ROW_LIMIT", 1):
			result = self._search("Xqzmonatsende")
		self.assertEqual(result["total"], 2, "counted, not the rows read")
		self.assertEqual([p["title"] for p in result["pages"]], ["Zum Xqzmonatsende"], "the title hit is the row read")

	def test_plain_text_for_the_search(self):
		from phamos.bookstack_integration.content import plain_text

		self.assertEqual(plain_text("<h2>Konten</h2><p>1200 <b>Bank</b></p>"), "Konten 1200 Bank")
