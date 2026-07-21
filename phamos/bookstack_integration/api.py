# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Server-side helpers used by the Bookstack Browser desk page."""

from __future__ import annotations

import frappe
from frappe import _


@frappe.whitelist()
def list_instances():
	"""Return the list of enabled Bookstack Configurations the user can read."""
	return frappe.get_all(
		"Bookstack Configuration",
		filters={"enabled": 1},
		fields=["name", "title", "instance_url"],
		order_by="title asc",
	)


@frappe.whitelist()
def get_tree(instance: str):
	"""Return the full shelves → books → chapters → pages hierarchy for an instance.

	Books not shelved anywhere are grouped under a synthetic "Unshelved" node so
	nothing is hidden from the user.
	"""
	if not instance:
		frappe.throw(_("Instance is required"))

	# Permission check on the configuration itself
	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")

	shelves = frappe.get_all(
		"Bookstack Shelf",
		filters={"instance": instance},
		fields=["name", "title", "bookstack_id", "url"],
		order_by="title asc",
	)
	books = frappe.get_all(
		"Bookstack Book",
		filters={"instance": instance},
		fields=["name", "title", "bookstack_id", "url", "shelf"],
		order_by="title asc",
	)
	chapters = frappe.get_all(
		"Bookstack Chapter",
		filters={"instance": instance},
		fields=["name", "title", "bookstack_id", "url", "book", "priority"],
		order_by="priority asc, title asc",
	)
	pages = frappe.get_all(
		"Bookstack Page",
		filters={"instance": instance},
		fields=["name", "title", "bookstack_id", "url", "book", "chapter", "priority", "draft"],
		order_by="priority asc, title asc",
	)

	# Index pages by (book, chapter). chapter can be empty (page directly under book).
	pages_by_chapter: dict[str, list[dict]] = {}
	pages_by_book_no_chapter: dict[str, list[dict]] = {}
	for p in pages:
		if p.chapter:
			pages_by_chapter.setdefault(p.chapter, []).append(_node(p, "page"))
		elif p.book:
			pages_by_book_no_chapter.setdefault(p.book, []).append(_node(p, "page"))

	chapters_by_book: dict[str, list[dict]] = {}
	for c in chapters:
		node = _node(c, "chapter")
		node["children"] = pages_by_chapter.get(c.name, [])
		chapters_by_book.setdefault(c.book, []).append(node)

	def build_book_node(b):
		node = _node(b, "book")
		node["children"] = chapters_by_book.get(b.name, []) + pages_by_book_no_chapter.get(b.name, [])
		return node

	books_by_shelf: dict[str, list[dict]] = {}
	unshelved: list[dict] = []
	for b in books:
		node = build_book_node(b)
		if b.shelf:
			books_by_shelf.setdefault(b.shelf, []).append(node)
		else:
			unshelved.append(node)

	tree: list[dict] = []
	for s in shelves:
		node = _node(s, "shelf")
		node["children"] = books_by_shelf.get(s.name, [])
		tree.append(node)

	if unshelved:
		tree.append({
			"type": "group",
			"title": _("Unshelved Books"),
			"name": None,
			"bookstack_id": None,
			"url": None,
			"children": unshelved,
		})

	return tree


@frappe.whitelist()
def get_node_detail(doctype: str, name: str):
	"""Return the full document for the right-side detail pane."""
	if doctype not in {
		"Bookstack Shelf",
		"Bookstack Book",
		"Bookstack Chapter",
		"Bookstack Page",
	}:
		frappe.throw(_("Invalid doctype"))
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return doc.as_dict()


@frappe.whitelist()
def get_page_html(instance: str, bookstack_id):
	"""Fetch the live rendered HTML of a Bookstack page via its REST API."""
	from phamos.bookstack_integration.api_client import BookstackClient

	frappe.get_doc("Bookstack Configuration", instance).check_permission("read")
	client = BookstackClient(instance)
	data = client.get(f"pages/{int(bookstack_id)}")
	return {
		"title": data.get("name"),
		"html": data.get("html") or "",
		"markdown": data.get("markdown") or "",
	}


def _node(row, kind: str) -> dict:
	return {
		"type": kind,
		"doctype": _DOCTYPE_BY_KIND[kind],
		"name": row.name,
		"title": row.title or row.name,
		"bookstack_id": row.bookstack_id,
		"url": row.url,
		"children": [],
	}


_DOCTYPE_BY_KIND = {
	"shelf": "Bookstack Shelf",
	"book": "Bookstack Book",
	"chapter": "Bookstack Chapter",
	"page": "Bookstack Page",
}
