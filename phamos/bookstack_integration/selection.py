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
from phamos.web_profile.docs import clear_cache as clear_docs_cache

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
	# Read is enough (decided 2026-11-21): showing the tree changes nothing; saving needs write.
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
	from phamos.bookstack_integration.sync import sync_lock

	config = frappe.get_doc("Bookstack Configuration", instance)
	config.check_permission("write")
	# Under the sync lock: a sync running meanwhile has read the old selection and would put the
	# removed records right back (review S8). A running sync makes this fail with SyncRunning.
	with sync_lock(instance):
		result = _save_sync_selection(instance, config, excluded)
		# Committed before the lock is released: a sync taking the lock right after must already
		# read the new selection, not the old one (review of !1275).
		frappe.db.commit()
		return result


def _save_sync_selection(instance: str, config, excluded) -> dict:

	rows = []
	seen = set()
	for row in frappe.parse_json(excluded) or []:
		item_type = row.get("item_type")
		if item_type not in ITEM_TYPES:
			frappe.throw(_("Unknown item type: {0}").format(item_type))
		bookstack_id = frappe.utils.cint(row.get("bookstack_id"))
		if bookstack_id <= 0:  # cint turns anything malformed into 0, which would match nothing
			frappe.throw(_("Invalid BookStack ID: {0}").format(row.get("bookstack_id")))
		if (item_type, bookstack_id) in seen:
			continue
		seen.add((item_type, bookstack_id))
		rows.append({
			"item_type": item_type,
			"bookstack_id": bookstack_id,
			"title": (row.get("title") or "")[:140],
		})
	config.set("sync_exclusions", rows)
	config.save()

	removed = remove_excluded(instance)
	# The public /de/doku pages (#2005) show the new state once it is committed.
	frappe.db.after_commit.add(clear_docs_cache)
	return {"excluded": len(rows), "removed": removed}


def _excluded_names(instance: str, excluded: dict[str, set[int]]) -> tuple[list[str], list[str]]:
	"""(chapters, pages) in ERPNext that the selection leaves out, including those under a
	left-out book or chapter. Book records themselves are kept (see remove_excluded)."""

	def names(doctype, filters_list):
		found = set()
		for f in filters_list:
			found.update(frappe.get_all(doctype, filters={"instance": instance, **f}, pluck="name"))
		return sorted(found)

	books = []
	if excluded["Book"]:
		books = frappe.get_all(
			"Bookstack Book", filters={"instance": instance, "bookstack_id": ["in", list(excluded["Book"])]}, pluck="name"
		)
	chapter_filters = [{"bookstack_id": ["in", list(excluded["Chapter"])]}] if excluded["Chapter"] else []
	if books:
		chapter_filters.append({"book": ["in", books]})
	chapters = names("Bookstack Chapter", chapter_filters)

	page_filters = [{"bookstack_id": ["in", list(excluded["Page"])]}] if excluded["Page"] else []
	if books:
		page_filters.append({"book": ["in", books]})
	if chapters:
		page_filters.append({"chapter": ["in", chapters]})
	return chapters, names("Bookstack Page", page_filters)


def remove_excluded(instance: str) -> int:
	"""Delete the ERPNext copies of the chapters and pages the instance leaves out, pages first.

	A left-out book keeps its record, with its "Publish on website" setting and its links on module
	pages (decided 2026-11-21): without pages it is not shown on the website, and ticking it again
	brings it back as it was. Bulk deletes: a big book has thousands of pages, too many for one
	delete_doc each in a web request; these records have no hooks or child tables.
	"""
	chapters, pages = _excluded_names(instance, exclusions(instance))
	if pages:
		frappe.db.delete("Bookstack Page", {"name": ["in", pages]})
	if chapters:
		frappe.db.delete("Bookstack Chapter", {"name": ["in", chapters]})
	return len(pages) + len(chapters)


@frappe.whitelist()
def preview_selection(instance: str, excluded) -> dict:
	"""What saving ``excluded`` would remove from ERPNext, for the dialog's confirmation."""
	frappe.get_doc("Bookstack Configuration", instance).check_permission("write")
	wanted = {t: set() for t in ITEM_TYPES}
	for row in frappe.parse_json(excluded) or []:
		if row.get("item_type") in ITEM_TYPES:
			wanted[row["item_type"]].add(frappe.utils.cint(row.get("bookstack_id")))
	chapters, pages = _excluded_names(instance, wanted)
	return {"chapters": len(chapters), "pages": len(pages)}
