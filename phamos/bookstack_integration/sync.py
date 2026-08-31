# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from __future__ import annotations

from typing import Any

import frappe
from frappe.utils import now_datetime

from phamos.bookstack_integration.api_client import BookstackAPIError, BookstackClient


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

def sync_shelves(client: BookstackClient, instance: str) -> int:
	count = 0
	for shelf in client.paginate("shelves"):
		detail = client.get(f"shelves/{shelf['id']}")
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
	return count


def sync_books(client: BookstackClient, instance: str) -> int:
	count = 0
	for book in client.paginate("books"):

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
	return count


def sync_chapters(client: BookstackClient, instance: str) -> int:
	count = 0
	for chapter in client.paginate("chapters"):
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
	return count


def _chapter_url(client: BookstackClient, chapter: dict, book_name: str | None, instance: str) -> str | None:
	slug = chapter.get("slug")
	if not (slug and book_name):
		return None
	book_slug = frappe.db.get_value("Bookstack Book", book_name, "slug")
	if not book_slug:
		return None
	return f"{client.base_url}/books/{book_slug}/chapter/{slug}"


def sync_pages(client: BookstackClient, instance: str) -> int:
	count = 0
	for page in client.paginate("pages"):
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
	return count


def _page_url(client: BookstackClient, page: dict, book_name: str | None) -> str | None:
	slug = page.get("slug")
	if not (slug and book_name):
		return None
	book_slug = frappe.db.get_value("Bookstack Book", book_name, "slug")
	if not book_slug:
		return None
	return f"{client.base_url}/books/{book_slug}/page/{slug}"



@frappe.whitelist()
def sync_instance(instance: str) -> dict[str, Any]:
	"""Full sync for a single Bookstack Configuration."""
	client = BookstackClient(instance)

	stats: dict[str, Any] = {"instance": instance}
	errors = 0

	steps = [
		("roles", sync_roles),
		("users", sync_users),
		("books", sync_books),        
		("shelves", sync_shelves),
		("chapters", sync_chapters),
		("pages", sync_pages),
	]

	for label, fn in steps:
		try:
			stats[label] = fn(client, instance)
		except Exception as exc:  
			errors += 1
			stats[label] = f"error: {exc}"
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {instance} :: {label}")

	frappe.db.set_value("Bookstack Configuration", instance, {
		"last_synced": now_datetime(),
		"sync_error_count": errors,
	})
	frappe.db.commit()
	stats["errors"] = errors
	return stats


@frappe.whitelist()
def sync_all_instances() -> list[dict[str, Any]]:
	"""Scheduler entry point — sync every enabled Bookstack Configuration."""
	results = []
	for name in frappe.get_all("Bookstack Configuration", filters={"enabled": 1}, pluck="name"):
		try:
			results.append(sync_instance(name))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"{LOG_TITLE} :: {name}")
	return results
