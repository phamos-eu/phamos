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

from phamos.bookstack_integration import selection, sync
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
			patch.object(selection, "BookstackClient", FakeBookstack),
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
		for role, expected in (("Bookstack User", 0), ("Bookstack Manager", 1)):
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


class TestChooseWhatToSync(_BookstackSyncCase):
	"""The "Sync…" dialog on Bookstack Configuration (phamos/phamos#2029)."""

	def _choose(self, steps, remove=1):
		return sync.sync_instance(INSTANCE, steps=steps, remove_deleted_records=remove)

	def _calls(self, steps, remove=1):
		"""Names of the steps sync_instance plans, without running them."""
		order = []

		def run(instance, plan):
			order.extend(name for name, _fn in plan)
			return {"errors": 0}

		with patch.object(sync, "_run_steps", side_effect=run):
			self._choose(steps, remove)
		return order

	def test_only_chosen_steps_run_in_fixed_order(self):
		self.assertEqual(self._calls(["content", "pages", "books"]), ["books", "pages", "removed", "content"])
		self.assertEqual(self._calls(["roles", "users"]), ["roles", "users"], "no removal without shelves/books/chapters/pages")
		self.assertEqual(self._calls(None), ["roles", "users", "books", "shelves", "chapters", "pages", "removed", "content"])

	def test_removal_can_be_switched_off(self):
		self._sync()
		FakeBookstack.data["pages"] = [p for p in FakeBookstack.data["pages"] if p["id"] != 102]

		self._choose(["books", "chapters", "pages"], remove=0)
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))

		self._choose(["books", "chapters", "pages"], remove=1)
		self.assertFalse(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-102"))

	def test_pages_only_leaves_users_alone(self):
		FakeBookstack.data["users"] = [{"id": 7, "name": "Neu", "email": "neu@example.test"}]

		self._choose(["books", "pages"])

		self.assertFalse(frappe.db.exists("Bookstack User", {"instance": INSTANCE, "bookstack_id": 7}))
		self.assertTrue(frappe.db.exists("Bookstack Page", f"{INSTANCE}-BSP-100"))

	def test_unknown_or_empty_choice_runs_nothing(self):
		with patch.object(sync, "_run_steps") as run:
			self.assertRaises(frappe.ValidationError, self._choose, ["pages", "everything"])
			self.assertRaises(frappe.ValidationError, self._choose, "[]")
			run.assert_not_called()

	def test_steps_arrive_as_json_from_the_dialog(self):
		self.assertEqual(self._calls('["pages"]', remove=0), ["pages"])


class TestSyncSelection(_BookstackSyncCase):
	"""Books, chapters and pages left out on the configuration (phamos/phamos#2029)."""

	def _exclude(self, *items):
		from phamos.bookstack_integration.selection import save_sync_selection

		return save_sync_selection(INSTANCE, [
			{"item_type": t, "bookstack_id": i, "title": f"{t} {i}"} for t, i in items
		])

	def _exists(self, doctype, bookstack_id):
		return frappe.db.exists(doctype, {"instance": INSTANCE, "bookstack_id": bookstack_id})

	def test_left_out_items_are_not_synced(self):
		self._exclude(("Book", 2), ("Chapter", 10), ("Page", 102))
		self._sync()

		self.assertFalse(self._exists("Bookstack Book", 2))
		self.assertFalse(self._exists("Bookstack Page", 200), "page of a left-out book")
		self.assertFalse(self._exists("Bookstack Chapter", 10))
		self.assertFalse(self._exists("Bookstack Page", 100), "page of a left-out chapter")
		self.assertFalse(self._exists("Bookstack Page", 102))
		self.assertTrue(self._exists("Bookstack Book", 1))
		self.assertTrue(self._exists("Bookstack Page", 101))

	def test_saving_removes_existing_copies(self):
		self._sync()
		self.assertTrue(self._exists("Bookstack Page", 100))

		result = self._exclude(("Chapter", 10), ("Book", 2))

		self.assertEqual(result, {"excluded": 2, "removed": 4})  # book 2, its page 200, chapter 10, its page 100
		self.assertFalse(self._exists("Bookstack Page", 100))
		self.assertFalse(self._exists("Bookstack Book", 2))
		self.assertTrue(self._exists("Bookstack Page", 102))

	def test_ticking_again_brings_items_back(self):
		self._exclude(("Book", 2))
		self._sync()
		self._exclude()
		self._sync()
		self.assertTrue(self._exists("Bookstack Page", 200))

	def test_tree_marks_left_out_items(self):
		from phamos.bookstack_integration.selection import get_sync_tree

		self._exclude(("Page", 102))
		tree = get_sync_tree(INSTANCE)

		self.assertEqual([b["title"] for b in tree], ["Handbuch", "Intern"])
		handbuch = tree[0]
		self.assertEqual([(c["type"], c["title"]) for c in handbuch["children"]],
			[("Chapter", "Start"), ("Page", "Zweite")], "chapters and loose pages by priority; drafts left out")
		self.assertEqual([p["title"] for p in handbuch["children"][0]["children"]], ["Erste"])
		self.assertFalse(handbuch["children"][1]["included"])
		self.assertTrue(handbuch["included"])

	def test_unknown_type_or_no_write_access_is_refused(self):
		self.assertRaises(frappe.ValidationError, self._exclude, ("Shelf", 1))
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.PermissionError, self._exclude, ("Book", 2))
		finally:
			frappe.set_user("Administrator")


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

	def test_dialog_choice_reaches_the_job(self):
		with patch.object(sync.frappe, "enqueue") as enqueue:
			sync.start_sync(INSTANCE, steps='["pages", "books"]', remove_deleted_records=0)
			kwargs = enqueue.call_args.kwargs
			self.assertEqual((kwargs["steps"], kwargs["remove_deleted_records"]), (["pages", "books"], 0))

			enqueue.reset_mock()
			self.assertRaises(frappe.ValidationError, sync.start_sync, INSTANCE, steps='["everything"]')
			enqueue.assert_not_called()

		with patch.object(sync, "_run_steps", return_value={"errors": 0}) as run, patch.object(sync.frappe, "publish_realtime"):
			sync.run_sync_job(INSTANCE, "someone@example.com", steps=["pages"], remove_deleted_records=0)
		self.assertEqual([name for name, _fn in run.call_args.args[1]], ["pages"])
