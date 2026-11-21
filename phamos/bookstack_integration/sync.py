# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from phamos.bookstack_integration.api_client import BookstackAPIError, BookstackClient
from phamos.bookstack_integration.content import clean_page_html, link_map_hash, published_link_map


LOG_TITLE = "Bookstack Sync"


def _iso(value: str | None) -> str | None:
	"""Bookstack returns ISO-8601 timestamps; Frappe expects space-separated."""
	if not value:
		return None
	return value.replace("T", " ").replace("Z", "").split(".")[0]


def _same(current, new) -> bool:
	"""Stored value equals what BookStack sent (dates, ints and empty values compared as text)."""
	if not current and not new:
		return True  # None, "" and 0 (how Frappe stores an empty Int or Check) are the same
	if isinstance(new, list):  # child table rows as [{"field": value}]
		return [{k: row.get(k) for k in item} for row, item in zip(current or [], new)] == new and len(current or []) == len(new)
	return frappe.utils.cstr(current) == frappe.utils.cstr(new)


def _upsert(doctype: str, instance: str, bookstack_id: int, values: dict) -> str:
	name = frappe.db.get_value(doctype, {"instance": instance, "bookstack_id": bookstack_id}, "name")
	values = {**values, "instance": instance, "bookstack_id": bookstack_id}
	if name:
		doc = frappe.get_doc(doctype, name)
		if all(_same(doc.get(k), v) for k, v in values.items()):
			# Nothing changed: no save, no hooks, no new "modified"; the hourly sync touches every
			# record, so this is most of them (review S10).
			frappe.db.set_value(doctype, name, "last_synced", now_datetime(), update_modified=False)
			return name
		doc.update({**values, "last_synced": now_datetime()})
		doc.save(ignore_permissions=True)
		return doc.name
	values["last_synced"] = now_datetime()
	values["doctype"] = doctype
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc.name


def _by_bookstack_id(doctype: str, instance: str, fields=("name",)) -> dict:
	"""{bookstack_id: row} of one instance, loaded once per step instead of once per item."""
	return {
		r.bookstack_id: r
		for r in frappe.get_all(doctype, filters={"instance": instance}, fields=["bookstack_id", *fields])
	}


def _lookup_name(doctype: str, instance: str, bookstack_id: int | None) -> str | None:
	if not bookstack_id:
		return None
	return frappe.db.get_value(doctype, {"instance": instance, "bookstack_id": bookstack_id}, "name")



def sync_roles(client: BookstackClient, instance: str) -> int:
	count = 0
	for role in client.paginate("roles"):
		_upsert("Bookstack Role", instance, role["id"], {
			"display_name": role.get("display_name"),
			"description": role.get("description"),
			"mfa_enforced": 1 if role.get("mfa_enforced") else 0,
			"external_auth_id": role.get("external_auth_id"),
			"created_at": _iso(role.get("created_at")),
			"updated_at": _iso(role.get("updated_at")),
		})
		count += 1
	return count


def sync_users(client: BookstackClient, instance: str) -> int:
	count = 0
	for user in client.paginate("users"):
		# Full detail (roles list) is only returned by GET /users/{id}
		try:
			detail = client.get(f"users/{user['id']}")
		except BookstackAPIError:
			detail = user

		roles = []
		for r in detail.get("roles", []) or []:
			role_name = _lookup_name("Bookstack Role", instance, r.get("id"))
			if role_name:
				roles.append({"role": role_name})

		erpnext_user = frappe.db.get_value("User", {"email": detail.get("email")}, "name")
		employee = None
		if erpnext_user:
			employee = frappe.db.get_value("Employee", {"user_id": erpnext_user}, "name")

		values = {
			"full_name": detail.get("name"),
			"email": detail.get("email"),
			"slug": detail.get("slug"),
			"external_auth_id": detail.get("external_auth_id"),
			"created_at": _iso(detail.get("created_at")),
			"updated_at": _iso(detail.get("updated_at")),
			"roles": roles,
		}
		if erpnext_user:
			values["erpnext_user"] = erpnext_user
		if employee:
			values["employee"] = employee

		_upsert("Bookstack User", instance, detail["id"], values)
		count += 1
	return count

def _owner_id(value):
	if isinstance(value, dict):
		return value.get("id")
	return value

def sync_shelves(client: BookstackClient, instance: str, seen: dict | None = None) -> int:
	count = 0
	ids = set()
	for shelf in client.paginate("shelves"):
		detail = client.get(f"shelves/{shelf['id']}")
		ids.add(detail["id"])
		books = []
		book_names = []
		for b in detail.get("books", []) or []:
			book_name = _lookup_name("Bookstack Book", instance, b.get("id"))
			if book_name:
				books.append({"book": book_name})
				book_names.append(book_name)

		shelf_name = _upsert("Bookstack Shelf", instance, detail["id"], {
			"title": detail.get("name"),
			"slug": detail.get("slug"),
			"description": detail.get("description"),
			"url": f"{client.base_url}/shelves/{detail.get('slug')}" if detail.get("slug") else None,
			"cover_url": (detail.get("cover") or {}).get("url"),
			"owned_by": _owner_id(detail.get("owned_by")),
			"created_at": _iso(detail.get("created_at")),
			"updated_at": _iso(detail.get("updated_at")),
			"books": books,
		})

		for book_name in book_names:
			book_doc = frappe.get_doc("Bookstack Book", book_name)
			if book_doc.get("shelf") != shelf_name:
				book_doc.shelf = shelf_name
				book_doc.save(ignore_permissions=True)

		count += 1
	if seen is not None:
		seen["Bookstack Shelf"] = ids
	return count


def sync_books(client: BookstackClient, instance: str, seen: dict | None = None) -> int:
	count = 0
	ids = set()
	for book in client.paginate("books"):
		ids.add(book["id"])
		_upsert("Bookstack Book", instance, book["id"], {
			"title": book.get("name"),
			"slug": book.get("slug"),
			"description": book.get("description"),
			"url": f"{client.base_url}/books/{book.get('slug')}" if book.get("slug") else None,
			"cover_url": (book.get("cover") or {}).get("url"),
			"owned_by": book.get("owned_by"),
			"created_at": _iso(book.get("created_at")),
			"updated_at": _iso(book.get("updated_at")),
		})
		count += 1
	if seen is not None:
		seen["Bookstack Book"] = ids
	return count


def sync_chapters(client: BookstackClient, instance: str, seen: dict | None = None) -> int:
	count = 0
	ids = set()
	books = _by_bookstack_id("Bookstack Book", instance, ("name", "slug"))
	for chapter in client.paginate("chapters"):
		ids.add(chapter["id"])
		book = books.get(chapter.get("book_id"))
		book_name = book.name if book else None
		_upsert("Bookstack Chapter", instance, chapter["id"], {
			"title": chapter.get("name"),
			"slug": chapter.get("slug"),
			"description": chapter.get("description"),
			"book": book_name,
			"priority": chapter.get("priority"),
			"url": _chapter_url(client, chapter, book),
			"owned_by": chapter.get("owned_by"),
			"created_at": _iso(chapter.get("created_at")),
			"updated_at": _iso(chapter.get("updated_at")),
		})
		count += 1
	if seen is not None:
		seen["Bookstack Chapter"] = ids
	return count


def _chapter_url(client: BookstackClient, chapter: dict, book) -> str | None:
	slug = chapter.get("slug")
	if not (slug and book and book.slug):
		return None
	return f"{client.base_url}/books/{book.slug}/chapter/{slug}"


def sync_pages(client: BookstackClient, instance: str, seen: dict | None = None) -> int:
	count = 0
	ids = set()
	books = _by_bookstack_id("Bookstack Book", instance, ("name", "slug"))
	chapters = _by_bookstack_id("Bookstack Chapter", instance)
	for page in client.paginate("pages"):
		ids.add(page["id"])
		book = books.get(page.get("book_id"))
		book_name = book.name if book else None
		chapter = chapters.get(page.get("chapter_id"))
		chapter_name = chapter.name if chapter else None
		_upsert("Bookstack Page", instance, page["id"], {
			"title": page.get("name"),
			"slug": page.get("slug"),
			"book": book_name,
			"chapter": chapter_name,
			"priority": page.get("priority"),
			"draft": 1 if page.get("draft") else 0,
			"template": 1 if page.get("template") else 0,
			"editor": page.get("editor"),
			"revision_count": page.get("revision_count"),
			"url": _page_url(client, page, book),
			"owned_by": page.get("owned_by"),
			"created_at": _iso(page.get("created_at")),
			"updated_at": _iso(page.get("updated_at")),
		})
		count += 1
	if seen is not None:
		seen["Bookstack Page"] = ids
	return count


def _page_url(client: BookstackClient, page: dict, book) -> str | None:
	slug = page.get("slug")
	if not (slug and book and book.slug):
		return None
	return f"{client.base_url}/books/{book.slug}/page/{slug}"



def sync_page_content(client: BookstackClient, instance: str) -> int:
	"""Copy the sanitised HTML of every page shown on the website (#2004).

	Only pages of books with "Publish on website" are fetched, and only when BookStack
	reports a newer version than the stored copy. Content of every other page is cleared,
	so a page that left a published book, or became a draft, is not shown any more.
	"""
	link_map = published_link_map(instance)
	# What is published changed (a book or page added, removed, renamed): every copy's links may
	# point to the wrong place, so all of them are fetched again (review S5).
	link_hash = link_map_hash(link_map)
	links_changed = frappe.db.get_value("Bookstack Configuration", instance, "website_link_hash") != link_hash
	books = frappe.get_all(
		"Bookstack Book", filters={"instance": instance, "publish_on_website": 1}, pluck="name"
	)
	pages = []
	if books:
		pages = frappe.get_all(
			"Bookstack Page",
			filters={"instance": instance, "book": ["in", books], "draft": 0, "template": 0},
			fields=["name", "bookstack_id", "updated_at", "content_updated_at"],
		)

	shown = [p.name for p in pages]
	page = frappe.qb.DocType("Bookstack Page")
	clear = (
		frappe.qb.update(page)
		.set(page.html, None)
		.set(page.content_updated_at, None)
		.where(page.instance == instance)
		.where(page.html.isnotnull() | page.content_updated_at.isnotnull())
	)
	if shown:
		clear = clear.where(page.name.notin(shown))
	clear.run()

	count = failed = 0
	for p in pages:
		if not links_changed and p.content_updated_at and p.content_updated_at == p.updated_at:
			continue
		try:
			data = client.get(f"pages/{p.bookstack_id}")
			frappe.db.set_value(
				"Bookstack Page",
				p.name,
				{
					"html": clean_page_html((data or {}).get("html") or "", client.base_url, link_map),
					"content_updated_at": p.updated_at,
				},
				update_modified=False,
			)
		except _JOB_TIMEOUT:
			raise
		except Exception:
			# One broken page must not stop the others; it is fetched again next time.
			failed += 1
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance} :: page {p.name}")
			continue
		count += 1
		if count % 25 == 0:
			frappe.db.commit()  # a first copy takes minutes: keep the progress if the job is stopped
	if not failed:
		# Only now: a page that failed keeps the old links and must be rewritten next run too.
		frappe.db.set_value("Bookstack Configuration", instance, "website_link_hash", link_hash, update_modified=False)
	return count


# Children first, so a parent is never removed while a record still points to it.
_REMOVAL_ORDER = ("Bookstack Page", "Bookstack Chapter", "Bookstack Book", "Bookstack Shelf")
# A parent is removed only when the lists of everything that points to it came in complete as well,
# or its children would keep links to a deleted record.
_CHILDREN = {
	"Bookstack Chapter": ("Bookstack Page",),
	"Bookstack Book": ("Bookstack Chapter", "Bookstack Page"),
	"Bookstack Shelf": ("Bookstack Book",),
}
# Never delete more than this share of an instance's records of one kind in one run (decided
# 2026-11-21): a bigger loss more likely means a broken answer than a cleaned-up wiki. Small
# instances may still delete a few records.
REMOVAL_MAX_SHARE = 0.2
REMOVAL_MIN_ALLOWED = 5


def remove_deleted(instance: str, seen: dict) -> int:
	"""Delete records that BookStack no longer returns.

	Only for doctypes whose list call finished in this run (they are keys of `seen`).
	An empty answer is not trusted: it more likely means a token without access
	than a wiki without content, so nothing is deleted then.
	"""
	removed = 0
	for doctype in _REMOVAL_ORDER:
		ids = seen.get(doctype)
		if not ids or any(not seen.get(child) for child in _CHILDREN.get(doctype, ())):
			continue
		stale = frappe.get_all(
			doctype,
			filters={"instance": instance, "bookstack_id": ["not in", list(ids)]},
			pluck="name",
		)
		total = frappe.db.count(doctype, {"instance": instance})
		if len(stale) > max(REMOVAL_MIN_ALLOWED, REMOVAL_MAX_SHARE * total):
			frappe.log_error(
				title=f"{LOG_TITLE} :: {instance} :: removal skipped",
				message=f"{len(stale)} of {total} {doctype} records of {instance} are missing in BookStack's "
				"answer; more than the sync removes in one run, so none were removed. Check the API token's access.",
			)
			continue
		for name in stale:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			removed += 1
		if doctype == "Bookstack Shelf" and stale:
			frappe.db.set_value("Bookstack Book", {"shelf": ["in", stale]}, "shelf", None)
	return removed


# A first copy of a big book takes minutes (one call per page); the lock outlives any run, and
# expires by itself if a worker dies mid-run.
SYNC_LOCK_SECONDS = 30 * 60


class SyncRunning(frappe.ValidationError):
	"""Another sync of the same Bookstack Configuration holds the lock."""


def _lock(instance: str):
	return frappe.cache.lock(frappe.cache.make_key(f"bookstack_sync:{instance}"), timeout=SYNC_LOCK_SECONDS)


def is_running(instance: str) -> bool:
	return _lock(instance).locked()


@contextmanager
def sync_lock(instance: str):
	"""One sync per instance at a time (#2004).

	Two syncs of one instance write the same records: they wait on each other's row locks until
	MariaDB gives up, and documents change under them. A manual sync started while the hourly job
	runs is refused; the scheduler skips an instance that is busy.
	"""
	lock = _lock(instance)
	if not lock.acquire(blocking=False):
		raise SyncRunning(_("A sync of {0} is already running. Try again when it has finished.").format(instance))
	try:
		yield lock
	finally:
		try:
			lock.release()
		except Exception:
			pass  # expired after SYNC_LOCK_SECONDS; nothing left to release


def _run_steps(instance: str, steps: list) -> dict[str, Any]:
	with sync_lock(instance) as lock:
		client = BookstackClient(instance)
		stats: dict[str, Any] = {"instance": instance}
		seen: dict[str, set] = {}
		errors = 0

		for label, fn in steps:
			try:
				lock.reacquire()  # a long run keeps the lock for another SYNC_LOCK_SECONDS
			except Exception:
				pass  # lost (expired): carry on; the worst case is the overlap the lock prevents
			try:
				if label == "removed":
					if errors:
						# A list that failed is incomplete: nothing is removed on a partial picture.
						stats[label] = "skipped: an earlier step failed"
						continue
					stats[label] = fn(instance, seen)
				elif label in _TRACKED_STEPS:
					stats[label] = fn(client, instance, seen)
				else:
					stats[label] = fn(client, instance)
			except _JOB_TIMEOUT:
				raise  # the job is out of time: stop now, so the lock is released in time
			except Exception as exc:
				errors += 1
				stats[label] = f"error: {exc}"
				frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance} :: {label}")

		stats["errors"] = errors
		return stats


_TRACKED_STEPS = {"shelves", "books", "chapters", "pages"}

try:  # rq's job timeout, raised inside the job; never swallowed by a step
	from rq.timeouts import JobTimeoutException as _JOB_TIMEOUT
except ImportError:  # pragma: no cover
	class _JOB_TIMEOUT(Exception):
		pass


def sync_instance(instance: str) -> dict[str, Any]:
	"""Full sync for a single Bookstack Configuration. Runs in a job or the scheduler, never in a
	web request: the buttons call start_sync (review S1)."""
	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")
	stats = _run_steps(instance, [
		("roles", sync_roles),
		("users", sync_users),
		("books", sync_books),
		("shelves", sync_shelves),
		("chapters", sync_chapters),
		("pages", sync_pages),
		("removed", remove_deleted),
		("content", sync_page_content),
	])
	frappe.db.set_value("Bookstack Configuration", instance, {
		"last_synced": now_datetime(),
		"sync_error_count": stats["errors"],
	})
	frappe.db.commit()
	return stats


def sync_published_instance(instance: str) -> dict[str, Any]:
	"""Books, chapters, pages and website content only; no users, roles or shelves."""
	stats = _run_steps(instance, [
		("books", sync_books),
		("chapters", sync_chapters),
		("pages", sync_pages),
		("removed", remove_deleted),
		("content", sync_page_content),
	])
	frappe.db.commit()
	return stats


def sync_all_instances() -> list[dict[str, Any]]:
	"""Scheduler entry point (daily_long) — sync every enabled Bookstack Configuration.
	Not whitelisted: it runs for minutes and belongs in a job, not a web request (review S1)."""
	results = []
	for name in frappe.get_all("Bookstack Configuration", filters={"enabled": 1}, pluck="name"):
		try:
			results.append(sync_instance(name))
		except SyncRunning:
			continue  # a manual sync of this instance is running; it does the same work
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {name}")
	return results


def sync_published_content() -> list[dict[str, Any]]:
	"""Hourly scheduler entry point: keep website content fresh for instances with published books."""
	instances = frappe.get_all(
		"Bookstack Book", filters={"publish_on_website": 1}, pluck="instance", distinct=True
	)
	results = []
	for name in instances:
		if not frappe.db.get_value("Bookstack Configuration", name, "enabled"):
			continue
		try:
			results.append(sync_published_instance(name))
		except SyncRunning:
			continue  # another sync of this instance is running; the next hour catches up
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {name}")
	return results


# --- manual sync in the background ----------------------------------------------------------------

REALTIME_EVENT = "bookstack_sync_done"


def _job_id(instance: str) -> str:
	return f"bookstack_sync::{instance}"


@frappe.whitelist()
def start_sync(instance: str) -> dict[str, Any]:
	"""The "Sync" buttons: queue a full sync of one instance and return at once (#2004).

	A first copy of a big book takes minutes, longer than a web request may run. The result
	reaches the user who started it as the realtime event ``bookstack_sync_done``.
	"""
	from frappe.utils.background_jobs import is_job_enqueued

	# Read is enough, Bookstack User included (decided 2026-11-21): the removal step only deletes
	# copies of records BookStack itself no longer has, so a sync cannot lose content.
	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")
	if is_running(instance) or is_job_enqueued(_job_id(instance)):
		raise SyncRunning(_("A sync of {0} is already running. Try again when it has finished.").format(instance))
	frappe.enqueue(
		"phamos.bookstack_integration.sync.run_sync_job",
		queue="long",
		timeout=SYNC_LOCK_SECONDS,
		job_id=_job_id(instance),
		deduplicate=True,
		instance=instance,
		user=frappe.session.user,
	)
	return {"queued": True}


def run_sync_job(instance: str, user: str) -> dict[str, Any]:
	"""Background job behind start_sync: run the sync, then tell the user who started it."""
	try:
		stats = sync_instance(instance)
	except Exception as exc:
		frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance}")
		stats = {"instance": instance, "errors": 1, "failed": str(exc)}
	frappe.publish_realtime(REALTIME_EVENT, stats, user=user, after_commit=False)
	return stats
