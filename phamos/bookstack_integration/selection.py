# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Which books, chapters and pages a Bookstack Configuration mirrors (phamos/phamos#2029).

The configuration keeps what is left out (table "sync_exclusions"); everything else is synced,
new items too. Leaving out a book or chapter leaves out everything under it, including pages
added later. Every sync respects it: the dialog, the daily full sync and the hourly content sync.
"""

from __future__ import annotations

import frappe
from frappe import _

from phamos.bookstack_integration.api_client import BookstackClient

ITEM_TYPES = ("Book", "Chapter", "Page")


def exclusions(instance: str) -> dict[str, set[int]]:
	"""{"Book": {ids}, "Chapter": {ids}, "Page": {ids}} of what the instance leaves out."""
	out = {t: set() for t in ITEM_TYPES}
	for row in frappe.get_all(
		"Bookstack Sync Exclusion",
		filters={"parenttype": "Bookstack Configuration", "parent": instance},
		fields=["item_type", "bookstack_id"],
	):
		out[row.item_type].add(row.bookstack_id)
	return out


def is_excluded(excluded: dict[str, set[int]], item_type: str, item: dict) -> bool:
	"""True for an item BookStack returned that is left out itself or sits in a left-out parent."""
	if item.get("book_id") in excluded["Book"] and item_type != "Book":
		return True
	if item_type == "Page" and item.get("chapter_id") in excluded["Chapter"]:
		return True
	return item.get("id") in excluded[item_type]


@frappe.whitelist()
def get_sync_tree(instance: str) -> list[dict]:
	"""Books → chapters → pages as BookStack has them now, each with ``included``.

	Loaded live, so items that were never synced show too. Drafts and templates are left out:
	the sync never mirrors them as content.
	"""
	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")
	client = BookstackClient(instance)
	excluded = exclusions(instance)

	def node(item_type, item, children=None):
		return {
			"type": item_type,
			"id": item["id"],
			"title": item.get("name") or item.get("slug") or str(item["id"]),
			"included": item["id"] not in excluded[item_type],
			"priority": item.get("priority") or 0,
			"children": children if children is not None else [],
		}

	books = list(client.paginate("books"))
	chapters = list(client.paginate("chapters"))
	pages = [p for p in client.paginate("pages") if not p.get("draft") and not p.get("template")]

	pages_by_chapter: dict[int, list] = {}
	loose_pages: dict[int, list] = {}
	for p in pages:
		if p.get("chapter_id"):
			pages_by_chapter.setdefault(p["chapter_id"], []).append(node("Page", p))
		else:
			loose_pages.setdefault(p.get("book_id"), []).append(node("Page", p))

	content_by_book: dict[int, list] = {}
	for c in chapters:
		children = sorted(pages_by_chapter.get(c["id"], []), key=lambda n: n["priority"])
		content_by_book.setdefault(c.get("book_id"), []).append(node("Chapter", c, children))
	for book_id, loose in loose_pages.items():
		content_by_book.setdefault(book_id, []).extend(loose)

	tree = [
		node("Book", b, sorted(content_by_book.get(b["id"], []), key=lambda n: n["priority"]))
		for b in books
	]
	return sorted(tree, key=lambda n: n["title"].lower())


@frappe.whitelist()
def save_sync_selection(instance: str, excluded) -> dict:
	"""Store what is left out and remove its copies from ERPNext at once.

	``excluded``: [{"item_type", "bookstack_id", "title"}], as the dialog sends it (list or JSON).
	"""
	config = frappe.get_doc("Bookstack Configuration", instance)
	config.check_permission("write")

	rows = []
	for row in frappe.parse_json(excluded) or []:
		item_type = row.get("item_type")
		if item_type not in ITEM_TYPES:
			frappe.throw(_("Unknown item type: {0}").format(item_type))
		rows.append({
			"item_type": item_type,
			"bookstack_id": frappe.utils.cint(row.get("bookstack_id")),
			"title": (row.get("title") or "")[:140],
		})
	config.set("sync_exclusions", rows)
	config.save()

	removed = remove_excluded(instance)
	return {"excluded": len(rows), "removed": removed}


def remove_excluded(instance: str) -> int:
	"""Delete the ERPNext copies of everything the instance leaves out, pages first."""
	excluded = exclusions(instance)

	def names(doctype, ids):
		if not ids:
			return []
		return frappe.get_all(doctype, filters={"instance": instance, "bookstack_id": ["in", list(ids)]}, pluck="name")

	books = names("Bookstack Book", excluded["Book"])
	chapter_filters = [{"instance": instance, "bookstack_id": ["in", list(excluded["Chapter"])]}] if excluded["Chapter"] else []
	if books:
		chapter_filters.append({"instance": instance, "book": ["in", books]})
	chapters = sorted({n for f in chapter_filters for n in frappe.get_all("Bookstack Chapter", filters=f, pluck="name")})

	page_filters = [{"instance": instance, "bookstack_id": ["in", list(excluded["Page"])]}] if excluded["Page"] else []
	if books:
		page_filters.append({"instance": instance, "book": ["in", books]})
	if chapters:
		page_filters.append({"instance": instance, "chapter": ["in", chapters]})
	pages = sorted({n for f in page_filters for n in frappe.get_all("Bookstack Page", filters=f, pluck="name")})

	removed = 0
	for doctype, todo in (("Bookstack Page", pages), ("Bookstack Chapter", chapters), ("Bookstack Book", books)):
		for name in todo:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
			removed += 1
	return removed
