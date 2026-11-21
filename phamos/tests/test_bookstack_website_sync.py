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
<!-- interne Notiz: nicht veröffentlichen -->
<a href="https://frappe.io" ping="https://tracker.test" name="cookie">Ping</a>
<div class="wp-stretched-link fixed-top" id="frappe">Überdeckt die Seite</div>
<img src="https://tracker.test/pixel.gif" alt="Fremd">
<pre><code class="language-python">x = 1</code></pre>
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


class _BookstackSyncCase(FrappeTestCase):
	"""Fake BookStack, a test configuration and a rollback; no tests of its own."""

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


class TestBookstackWebsiteSync(_BookstackSyncCase):
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
		# review S6: no comments, ping, name, foreign classes or ids
		for unsafe in ("interne Notiz", "ping=", 'name="cookie"', "wp-stretched-link", "fixed-top", 'id="frappe"'):
			self.assertNotIn(unsafe, html)
		self.assertIn("Überdeckt die Seite", html, "the text stays, only the attributes go")
		self.assertIn('class="language-python"', html)
		# images only from the BookStack host (privacy, 2026-11-21)
		self.assertNotIn("tracker.test", html)

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

	def test_only_managers_can_publish(self):
		self._sync()
		name = f"{INSTANCE}-BSB-1"
		for role, expected in (("Bookstack User", 0), ("Bookstack Manager", 1), ("Website Manager", 1)):
			email = f"bs-website-{role.split()[1].lower()}@example.com"
			if not frappe.db.exists("User", email):
				frappe.get_doc({
					"doctype": "User", "email": email, "first_name": role, "send_welcome_email": 0,
					"roles": [{"role": role}],
				}).insert(ignore_permissions=True)
			frappe.db.set_value("Bookstack Book", name, "publish_on_website", 0)
			frappe.set_user(email)
			try:
				book = frappe.get_doc("Bookstack Book", name)
				book.publish_on_website = 1
				book.save()
			finally:
				frappe.set_user("Administrator")
			self.assertEqual(frappe.db.get_value("Bookstack Book", name, "publish_on_website"), expected, role)

	def test_sync_needs_access_to_the_configuration(self):
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.PermissionError, sync.sync_instance, INSTANCE)
		finally:
			frappe.set_user("Administrator")

	def test_only_the_background_start_is_callable_from_the_browser(self):
		# The synchronous syncs run for minutes; a web request would be cut off holding the lock (S1).
		whitelisted = {getattr(f, "__name__", "") for f in frappe.whitelisted if getattr(f, "__module__", "") == sync.__name__}
		self.assertEqual(whitelisted, {"start_sync"})

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


class TestSyncLockAndBackground(_BookstackSyncCase):
	"""One sync per instance at a time; "Sync All" runs as a background job (#2004)."""

	def test_second_sync_is_refused_while_one_runs(self):
		with sync.sync_lock(INSTANCE):
			self.assertTrue(sync.is_running(INSTANCE))
			self.assertRaises(sync.SyncRunning, self._sync)
		self.assertFalse(sync.is_running(INSTANCE))
		self._sync()  # free again

	def test_hourly_job_skips_a_busy_instance_quietly(self):
		self._sync()
		self._publish(1)
		errors_before = frappe.db.count("Error Log")
		real = sync.sync_published_instance

		def only_this_test(name):
			# Other configurations on the site (real BookStack instances) are not touched.
			return real(name) if name == INSTANCE else {"instance": name}

		with patch.object(sync, "sync_published_instance", side_effect=only_this_test), sync.sync_lock(INSTANCE):
			results = sync.sync_published_content()
		self.assertNotIn(INSTANCE, [r["instance"] for r in results])
		self.assertEqual(frappe.db.count("Error Log"), errors_before)

	def test_lock_is_freed_when_a_sync_fails(self):
		with patch.object(sync, "BookstackClient", side_effect=RuntimeError("no connection")):
			self.assertRaises(RuntimeError, self._sync)
		self.assertFalse(sync.is_running(INSTANCE))

	def test_sync_all_queues_one_background_job(self):
		with patch.object(sync.frappe, "enqueue") as enqueue:
			self.assertEqual(sync.start_sync(INSTANCE), {"queued": True})
			kwargs = enqueue.call_args.kwargs
			self.assertEqual(enqueue.call_args.args[0], "phamos.bookstack_integration.sync.run_sync_job")
			self.assertEqual((kwargs["queue"], kwargs["job_id"], kwargs["deduplicate"]),
				("long", f"bookstack_sync::{INSTANCE}", True))
			self.assertEqual(kwargs["instance"], INSTANCE)

			enqueue.reset_mock()
			with sync.sync_lock(INSTANCE):
				self.assertRaises(sync.SyncRunning, sync.start_sync, INSTANCE)
			enqueue.assert_not_called()

	def test_sync_all_needs_access_to_the_configuration(self):
		frappe.set_user("Guest")
		try:
			with patch.object(sync.frappe, "enqueue") as enqueue:
				self.assertRaises(frappe.PermissionError, sync.start_sync, INSTANCE)
				enqueue.assert_not_called()
		finally:
			frappe.set_user("Administrator")

	def test_job_reports_the_result_to_the_user_who_started_it(self):
		def sync_events(publish):
			# Frappe also publishes ordinary list updates while records are saved.
			return [c for c in publish.call_args_list if c.args and c.args[0] == sync.REALTIME_EVENT]

		with patch.object(sync.frappe, "publish_realtime") as publish:
			stats = sync.run_sync_job(INSTANCE, "someone@example.com")
		self.assertEqual(stats["errors"], 0)
		[event] = sync_events(publish)
		self.assertEqual(event.args[1], stats)
		self.assertEqual(event.kwargs["user"], "someone@example.com")

		with patch.object(sync.frappe, "publish_realtime") as publish, sync.sync_lock(INSTANCE):
			stats = sync.run_sync_job(INSTANCE, "someone@example.com")
		self.assertIn("already running", stats["failed"])
		self.assertEqual(len(sync_events(publish)), 1)


class TestReviewFixes(_BookstackSyncCase):
	"""Findings of the review of !1270 (2026-11-21)."""

	def test_incomplete_list_from_bookstack_fails_the_step(self):
		from phamos.bookstack_integration.api_client import BookstackClient

		client = BookstackClient.__new__(BookstackClient)
		answers = iter([{"data": [{"id": 1}, {"id": 2}], "total": 5}, {"data": [], "total": 5}])
		with patch.object(BookstackClient, "get", side_effect=lambda *a, **k: next(answers)):
			got = []
			with self.assertRaises(BookstackAPIError):
				for item in client.paginate("books", page_size=2):
					got.append(item)
		self.assertEqual(len(got), 2, "items received are still handed on")

		answers = iter([{"data": [{"id": 1}, {"id": 2}], "total": 4}, None])
		with patch.object(BookstackClient, "get", side_effect=lambda *a, **k: next(answers)):
			with self.assertRaises(BookstackAPIError):
				list(client.paginate("books", page_size=2))

	def test_no_removal_after_a_failed_list(self):
		self._sync()
		FakeBookstack.data["pages"] = [p for p in FakeBookstack.data["pages"] if p["id"] != 102]
		FakeBookstack.failing = {"chapters"}
		stats = self._sync()
		self.assertTrue(str(stats["removed"]).startswith("skipped"))
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))

	def test_parent_removed_only_when_its_children_were_listed(self):
		self._sync()
		seen = {"Bookstack Book": {2}}  # book 1 missing, but chapters and pages were not listed
		self.assertEqual(sync.remove_deleted(INSTANCE, seen), 0)
		self.assertTrue(frappe.db.exists("Bookstack Book", f"{INSTANCE}-BSB-1"))

	def test_mass_removal_is_refused(self):
		self._sync()
		with patch.object(sync, "REMOVAL_MIN_ALLOWED", 1):
			# 3 of 4 pages missing: more than 20 %, so nothing goes
			removed = sync.remove_deleted(INSTANCE, {"Bookstack Page": {100}})
		self.assertEqual(removed, 0)
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))

	def test_unchanged_records_are_not_saved_again(self):
		self._sync()
		before = frappe.db.get_value("Bookstack Page", f"{INSTANCE}-BSP-100", "modified")
		self._sync()
		self.assertEqual(frappe.db.get_value("Bookstack Page", f"{INSTANCE}-BSP-100", "modified"), before)

		FakeBookstack.data["pages"][0]["name"] = "Erste (neu)"
		self._sync()
		self.assertEqual(frappe.db.get_value("Bookstack Page", f"{INSTANCE}-BSP-100", "title"), "Erste (neu)")

	def test_new_unpublished_book_does_not_refetch_published_pages(self):
		self._sync()
		self._publish(1)
		self._sync()
		FakeBookstack.fetched = []
		FakeBookstack.data["books"].append({"id": 3, "name": "Neu", "slug": "neu", "updated_at": "2026-11-01T10:00:00.000000Z"})
		self._sync()
		self.assertEqual(FakeBookstack.fetched, [])

	def test_published_page_added_rewrites_links_everywhere(self):
		self._sync()
		self._publish(1)
		self._sync()
		FakeBookstack.fetched = []
		FakeBookstack.data["pages"].append({"id": 103, "book_id": 1, "name": "Dritte", "slug": "dritte",
			"priority": 3, "updated_at": "2026-11-01T10:00:00.000000Z"})
		self._sync()
		self.assertCountEqual(FakeBookstack.fetched, [100, 102, 103], "the link map changed, so every copy is refreshed")

	def test_one_broken_page_does_not_stop_the_others(self):
		self._sync()
		self._publish(1)
		real = sync.clean_page_html

		def broken_for_100(html, base, link_map):
			if FakeBookstack.fetched[-1] == 100:
				raise ValueError("parser")
			return real(html, base, link_map)

		with patch.object(sync, "clean_page_html", side_effect=broken_for_100):
			stats = self._sync()
		self.assertEqual(stats["errors"], 0)
		self.assertIsNone(_page(100))
		self.assertIn("Zelle", _page(102))

	def test_job_timeout_is_not_swallowed(self):
		self._sync()
		with patch.object(sync, "sync_pages", side_effect=sync._JOB_TIMEOUT("out of time")):
			self.assertRaises(sync._JOB_TIMEOUT, self._sync)
		self.assertFalse(sync.is_running(INSTANCE), "the lock is released")

	def test_image_without_source_is_removed(self):
		from phamos.bookstack_integration.content import clean_page_html

		html = clean_page_html('<p>a</p><img alt="leer"><img src="  "><img src="/uploads/x.png">', BASE,
			{"books": set(), "pages": set(), "page_ids": {}})
		self.assertEqual(html.count("<img"), 1)
		self.assertIn(f'src="{BASE}/uploads/x.png"', html)

	def test_books_are_removed_in_a_wiki_without_chapters(self):
		FakeBookstack.data["chapters"] = []
		for p in FakeBookstack.data["pages"]:
			p.pop("chapter_id", None)
		self._sync()
		self.assertTrue(frappe.db.exists("Bookstack Book", f"{INSTANCE}-BSB-2"))

		FakeBookstack.data["books"] = [b for b in FakeBookstack.data["books"] if b["id"] != 2]
		FakeBookstack.data["pages"] = [p for p in FakeBookstack.data["pages"] if p["book_id"] != 2]
		self._sync()
		self.assertFalse(frappe.db.exists("Bookstack Book", f"{INSTANCE}-BSB-2"))

	def test_interrupted_link_refresh_resumes_where_it_stopped(self):
		from rq.timeouts import JobTimeoutException

		self._sync()
		self._publish(1)
		self._sync()
		self._publish(2)  # links to book 2 change: every copy needs new links
		FakeBookstack.fetched = []
		real_get = FakeBookstack.get

		def stop_after_first(client, path, params=None):
			if FakeBookstack.fetched:
				raise JobTimeoutException("stopped")
			return real_get(client, path, params)

		with patch.object(FakeBookstack, "get", stop_after_first):
			self.assertRaises(JobTimeoutException, self._sync)
		first = list(FakeBookstack.fetched)
		self.assertEqual(len(first), 1)

		FakeBookstack.fetched = []
		self._sync()
		self.assertEqual(sorted(FakeBookstack.fetched + first), [100, 102, 200], "each page once, none twice")

