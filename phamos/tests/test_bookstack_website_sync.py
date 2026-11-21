# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Website copy of published BookStack books (phamos/phamos#2004).

The sync runs against a fake BookStack, so no network is needed. Run with
    bench --site <site> run-tests --module phamos.tests.test_bookstack_website_sync
"""

from copy import deepcopy
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.bookstack_integration import sync
from phamos.bookstack_integration.api_client import BookstackAPIError

INSTANCE = "BS Website Test"
BASE = "https://doku.example.test"

PAGE_HTML = f"""
<h2 id="bkmrk-intro">Intro</h2>
<p class="callout info" onclick="steal()">Hinweis</p>
<script>alert("x")</script>
<style>body {{ display: none }}</style>
<form action="https://evil.test"><input name="q"></form>
<table><tr><td>Zelle</td></tr></table>
<p style="position: fixed; z-index: 999; top: 0; text-align: center" data-wp-contact="x">Mitte</p>
<img src="/uploads/images/bild.png" alt="Bild">
<a href="{BASE}/books/handbuch/page/zweite#bkmrk-a">Zweite</a>
<a href="/books/intern/page/geheim">Intern</a>
<a href="{BASE}/link/102">Permalink</a>
<a href="{BASE}/books/handbuch/chapter/start">Kapitel</a>
<a href="{BASE}/books/handbuch/page/entwurf">Entwurf</a>
<a href="https://frappe.io/erpnext">Extern</a>
<a href="javascript:alert(1)">Böse</a>
"""

DATA = {
	"books": [
		{"id": 1, "name": "Handbuch", "slug": "handbuch", "updated_at": "2026-11-01T10:00:00.000000Z"},
		{"id": 2, "name": "Intern", "slug": "intern", "updated_at": "2026-11-01T10:00:00.000000Z"},
	],
	"chapters": [{"id": 10, "book_id": 1, "name": "Start", "slug": "start", "priority": 1}],
	"pages": [
		{"id": 100, "book_id": 1, "chapter_id": 10, "name": "Erste", "slug": "erste", "priority": 1,
			"updated_at": "2026-11-01T10:00:00.000000Z"},
		{"id": 101, "book_id": 1, "name": "Entwurf", "slug": "entwurf", "draft": True,
			"updated_at": "2026-11-01T10:00:00.000000Z"},
		{"id": 102, "book_id": 1, "name": "Zweite", "slug": "zweite", "priority": 2,
			"updated_at": "2026-11-01T10:00:00.000000Z"},
		{"id": 200, "book_id": 2, "name": "Geheim", "slug": "geheim",
			"updated_at": "2026-11-01T10:00:00.000000Z"},
	],
}


class FakeBookstack:
	"""Answers like BookStack's REST API; records which pages were fetched."""

	data: dict = {}
	fetched: list = []
	failing: set = set()

	def __init__(self, instance):
		self.base_url = BASE

	def paginate(self, path, params=None, page_size=None):
		if path in FakeBookstack.failing:
			raise BookstackAPIError(500, "down")
		yield from FakeBookstack.data.get(path, [])

	def get(self, path, params=None):
		page_id = int(path.split("/")[1])
		FakeBookstack.fetched.append(page_id)
		return {"id": page_id, "html": PAGE_HTML}


def _page(bookstack_id, field="html"):
	return frappe.db.get_value("Bookstack Page", f"{INSTANCE}-BSP-{bookstack_id}", field)


class TestBookstackWebsiteSync(FrappeTestCase):
	def setUp(self):
		frappe.db.savepoint("bookstack_website_sync")
		if not frappe.db.exists("Bookstack Configuration", INSTANCE):
			frappe.get_doc({
				"doctype": "Bookstack Configuration", "title": INSTANCE, "enabled": 1,
				"instance_url": BASE, "token_id": "id", "token_secret": "secret",
			}).insert(ignore_permissions=True)
		FakeBookstack.data = deepcopy(DATA)
		FakeBookstack.fetched = []
		FakeBookstack.failing = set()
		patches = [
			patch.object(sync, "BookstackClient", FakeBookstack),
			patch.object(frappe.db, "commit"),
		]
		for p in patches:
			p.start()
			self.addCleanup(p.stop)

	def tearDown(self):
		frappe.db.rollback(save_point="bookstack_website_sync")

	def _sync(self):
		return sync.sync_published_instance(INSTANCE)

	def _publish(self, bookstack_id, value=1):
		book = frappe.get_doc("Bookstack Book", f"{INSTANCE}-BSB-{bookstack_id}")
		book.publish_on_website = value
		book.save(ignore_permissions=True)

	def test_only_pages_of_published_books_get_content(self):
		self._sync()
		self.assertEqual(FakeBookstack.fetched, [])
		self.assertIsNone(_page(100))

		self._publish(1)
		self._sync()

		self.assertCountEqual(FakeBookstack.fetched, [100, 102])
		self.assertIn("Zelle", _page(100))
		self.assertIn("Zelle", _page(102))
		self.assertIsNone(_page(101), "drafts are not copied")
		self.assertIsNone(_page(200), "pages of unpublished books are not copied")

	def test_unchanged_page_is_not_fetched_again(self):
		self._sync()
		self._publish(1)
		self._sync()
		FakeBookstack.fetched = []

		self._sync()
		self.assertEqual(FakeBookstack.fetched, [])

		FakeBookstack.data["pages"][0]["updated_at"] = "2026-11-02T09:00:00.000000Z"
		self._sync()
		self.assertEqual(FakeBookstack.fetched, [100])

	def test_html_is_made_safe(self):
		self._sync()
		self._publish(1)
		self._sync()
		html = _page(100)

		for unsafe in ("<script", "alert(", "<style", "display: none", "<form", "<input", "onclick", "javascript:"):
			self.assertNotIn(unsafe, html)
		for unsafe in ("position", "z-index", "data-wp-contact"):
			self.assertNotIn(unsafe, html, "styles and data attributes that could cover the site")
		self.assertIn('style="text-align: center;"', html)
		self.assertIn('<table>', html)
		self.assertIn('id="bkmrk-intro"', html)
		self.assertIn('class="callout info"', html)
		self.assertIn(f'src="{BASE}/uploads/images/bild.png"', html)
		self.assertIn('loading="lazy"', html)

	def test_links_to_published_pages_stay_on_the_website(self):
		self._sync()
		self._publish(1)
		self._sync()
		html = _page(100)

		self.assertIn('href="/de/doku/handbuch/zweite#bkmrk-a"', html)
		self.assertIn('href="/de/doku/handbuch/zweite"', html, "permalink /link/<id>")
		self.assertIn('href="/de/doku/handbuch#start"', html, "chapter link")
		self.assertIn(f'href="{BASE}/books/intern/page/geheim"', html, "unpublished book stays on BookStack")
		self.assertIn(f'href="{BASE}/books/handbuch/page/entwurf"', html, "draft stays on BookStack")
		self.assertIn('href="https://frappe.io/erpnext"', html)

	def test_publishing_another_book_refreshes_links(self):
		self._sync()
		self._publish(1)
		self._sync()
		FakeBookstack.fetched = []

		self._publish(2)
		self._sync()

		self.assertCountEqual(FakeBookstack.fetched, [100, 102, 200])
		self.assertIn('href="/de/doku/intern/geheim"', _page(100))

	def test_unpublishing_clears_content(self):
		self._sync()
		self._publish(1)
		self._sync()

		self._publish(1, 0)

		self.assertIsNone(_page(100))
		self.assertIsNone(_page(100, "content_updated_at"))

	def test_records_deleted_in_bookstack_are_removed(self):
		self._sync()
		self._publish(1)
		self._sync()

		FakeBookstack.data["pages"] = [p for p in FakeBookstack.data["pages"] if p["id"] != 102]
		FakeBookstack.data["chapters"] = [{"id": 11, "book_id": 1, "name": "Neu", "slug": "neu"}]
		self._sync()

		self.assertFalse(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))
		self.assertFalse(frappe.db.exists("Bookstack Chapter", f"{INSTANCE}-BSC-10"))
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-100"))

	def test_sync_needs_access_to_the_configuration(self):
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.PermissionError, sync.sync_instance, INSTANCE)
			self.assertRaises(frappe.PermissionError, sync.sync_all_instances)
		finally:
			frappe.set_user("Administrator")

	def test_nothing_is_removed_when_bookstack_fails_or_returns_nothing(self):
		self._sync()

		FakeBookstack.failing = {"pages"}
		stats = self._sync()
		self.assertEqual(stats["errors"], 1)
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))

		FakeBookstack.failing = set()
		FakeBookstack.data["pages"] = []
		self._sync()
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))
