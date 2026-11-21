# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe import _
from frappe.utils import now_datetime

from phamos.bookstack_integration.api_client import BookstackAPIError, BookstackClient
from phamos.bookstack_integration.content import clean_page_html, published_link_map
from phamos.bookstack_integration.selection import exclusions, is_excluded


LOG_TITLE = "Bookstack Sync"


def _iso(value: str | None) -> str | None:
	"""Bookstack returns ISO-8601 timestamps; Frappe expects space-separated."""
	if not value:
		return None
	return value.replace("T", " ").replace("Z", "").split(".")[0]


def _upsert(doctype: str, instance: str, bookstack_id: int, values: dict) -> str:
	name = frappe.db.get_value(doctype, {"instance": instance, "bookstack_id": bookstack_id}, "name")
	values = {**values, "instance": instance, "bookstack_id": bookstack_id, "last_synced": now_datetime()}
	if name:
		doc = frappe.get_doc(doctype, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc.name
	values["doctype"] = doctype
	doc = frappe.get_doc(values)
	doc.insert(ignore_permissions=True)
	return doc.name


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
	excluded = exclusions(instance)
	for book in client.paginate("books"):
		if is_excluded(excluded, "Book", book):
			continue  # left out on the configuration (#2029)
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
	excluded = exclusions(instance)
	for chapter in client.paginate("chapters"):
		if is_excluded(excluded, "Chapter", chapter):
			continue  # left out on the configuration (#2029)
		ids.add(chapter["id"])
		book_name = _lookup_name("Bookstack Book", instance, chapter.get("book_id"))
		_upsert("Bookstack Chapter", instance, chapter["id"], {
			"title": chapter.get("name"),
			"slug": chapter.get("slug"),
			"description": chapter.get("description"),
			"book": book_name,
			"priority": chapter.get("priority"),
			"url": _chapter_url(client, chapter, book_name, instance),
			"owned_by": chapter.get("owned_by"),
			"created_at": _iso(chapter.get("created_at")),
			"updated_at": _iso(chapter.get("updated_at")),
		})
		count += 1
	if seen is not None:
		seen["Bookstack Chapter"] = ids
	return count


def _chapter_url(client: BookstackClient, chapter: dict, book_name: str | None, instance: str) -> str | None:
	slug = chapter.get("slug")
	if not (slug and book_name):
		return None
	book_slug = frappe.db.get_value("Bookstack Book", book_name, "slug")
	if not book_slug:
		return None
	return f"{client.base_url}/books/{book_slug}/chapter/{slug}"


def sync_pages(client: BookstackClient, instance: str, seen: dict | None = None) -> int:
	count = 0
	ids = set()
	excluded = exclusions(instance)
	for page in client.paginate("pages"):
		if is_excluded(excluded, "Page", page):
			continue  # left out on the configuration (#2029)
		ids.add(page["id"])
		book_name = _lookup_name("Bookstack Book", instance, page.get("book_id"))
		chapter_name = _lookup_name("Bookstack Chapter", instance, page.get("chapter_id"))
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
			"url": _page_url(client, page, book_name),
			"owned_by": page.get("owned_by"),
			"created_at": _iso(page.get("created_at")),
			"updated_at": _iso(page.get("updated_at")),
		})
		count += 1
	if seen is not None:
		seen["Bookstack Page"] = ids
	return count


def _page_url(client: BookstackClient, page: dict, book_name: str | None) -> str | None:
	slug = page.get("slug")
	if not (slug and book_name):
		return None
	book_slug = frappe.db.get_value("Bookstack Book", book_name, "slug")
	if not book_slug:
		return None
	return f"{client.base_url}/books/{book_slug}/page/{slug}"



def sync_page_content(client: BookstackClient, instance: str) -> int:
	"""Copy the sanitised HTML of every page shown on the website (#2004).

	Only pages of books with "Publish on website" are fetched, and only when BookStack
	reports a newer version than the stored copy. Content of every other page is cleared,
	so a page that left a published book, or became a draft, is not shown any more.
	"""
	link_map = published_link_map(instance)
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

	count = 0
	for p in pages:
		if p.content_updated_at and p.content_updated_at == p.updated_at:
			continue
		try:
			data = client.get(f"pages/{p.bookstack_id}")
		except BookstackAPIError:
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance} :: page {p.bookstack_id}")
			continue
		frappe.db.set_value(
			"Bookstack Page",
			p.name,
			{
				"html": clean_page_html(data.get("html") or "", client.base_url, link_map),
				"content_updated_at": p.updated_at,
			},
			update_modified=False,
		)
		count += 1
	return count


# Children first, so a parent is never removed while a record still points to it.
_REMOVAL_ORDER = ("Bookstack Page", "Bookstack Chapter", "Bookstack Book", "Bookstack Shelf")


def remove_deleted(instance: str, seen: dict) -> int:
	"""Delete records that BookStack no longer returns.

	Only for doctypes whose list call finished in this run (they are keys of `seen`).
	An empty answer is not trusted: it more likely means a token without access
	than a wiki without content, so nothing is deleted then.
	"""
	removed = 0
	for doctype in _REMOVAL_ORDER:
		ids = seen.get(doctype)
		if not ids:
			continue
		stale = frappe.get_all(
			doctype,
			filters={"instance": instance, "bookstack_id": ["not in", list(ids)]},
			pluck="name",
		)
		for name in stale:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			removed += 1
		if doctype == "Bookstack Shelf" and stale:
			frappe.db.set_value("Bookstack Book", {"shelf": ["in", stale]}, "shelf", None)
	return removed


def _run_steps(instance: str, steps: list) -> dict[str, Any]:
	client = BookstackClient(instance)
	stats: dict[str, Any] = {"instance": instance}
	seen: dict[str, set] = {}
	errors = 0

	for label, fn in steps:
		try:
			if label == "removed":
				stats[label] = fn(instance, seen)
			elif label in _TRACKED_STEPS:
				stats[label] = fn(client, instance, seen)
			else:
				stats[label] = fn(client, instance)
		except Exception as exc:
			errors += 1
			stats[label] = f"error: {exc}"
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance} :: {label}")

	stats["errors"] = errors
	return stats


_TRACKED_STEPS = {"shelves", "books", "chapters", "pages"}


# Every step of a full sync, in the order it must run: users link roles, shelves and chapters link
# books, pages link books and chapters, the website copy reads pages (#2029).
SYNC_STEPS = {
	"roles": sync_roles,
	"users": sync_users,
	"books": sync_books,
	"shelves": sync_shelves,
	"chapters": sync_chapters,
	"pages": sync_pages,
	"content": sync_page_content,
}


@frappe.whitelist()
def sync_instance(instance: str, steps=None, remove_deleted_records=1) -> dict[str, Any]:
	"""Sync one Bookstack Configuration: every step, or only ``steps`` (names from SYNC_STEPS).

	The chosen steps always run in SYNC_STEPS order. ``remove_deleted_records`` deletes the shelves,
	books, chapters and pages BookStack no longer returns, for the chosen ones of those only; it runs
	after them and before the website copy, so a deleted page is not copied.
	"""
	# Whitelisted for the "Sync" buttons; the sync deletes records, so not for every logged-in user.
	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")

	chosen = frappe.parse_json(steps) if steps else list(SYNC_STEPS)
	unknown = set(chosen) - set(SYNC_STEPS)
	if unknown:
		frappe.throw(_("Unknown sync step: {0}").format(", ".join(sorted(unknown))))
	if not chosen:
		frappe.throw(_("Choose at least one part to sync."))

	plan = [(name, fn) for name, fn in SYNC_STEPS.items() if name in chosen]
	if frappe.utils.cint(remove_deleted_records) and _TRACKED_STEPS & set(chosen):
		at = next((i for i, (name, _fn) in enumerate(plan) if name == "content"), len(plan))
		plan.insert(at, ("removed", remove_deleted))

	stats = _run_steps(instance, plan)
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


@frappe.whitelist()
def sync_all_instances() -> list[dict[str, Any]]:
	"""Scheduler entry point — sync every enabled Bookstack Configuration."""
	# Whitelisted, but only for those who manage the configurations (the scheduler runs as Administrator).
	frappe.has_permission("Bookstack Configuration", "write", throw=True)
	results = []
	for name in frappe.get_all("Bookstack Configuration", filters={"enabled": 1}, pluck="name"):
		try:
			results.append(sync_instance(name))
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
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {name}")
	return results
