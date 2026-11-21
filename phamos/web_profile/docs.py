# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Public documentation under /de/doku, built from BookStack books (phamos/phamos#2005).

Only books with "Publish on website" are shown, and only their pages whose content the sync has
copied (Bookstack Page.html, phamos/phamos#2004). Nothing is fetched from BookStack per visit.
URLs use BookStack's slugs: /de/doku/<book>/<page>.
"""

from __future__ import annotations

import frappe
from bs4 import BeautifulSoup

from phamos.bookstack_integration.content import DOCS_ROUTE

CACHE_KEY = "web_docs"
CACHE_SECONDS = 600


def clear_cache():
	"""Called at the end of every BookStack sync and when a book changes."""
	frappe.cache.delete_value(CACHE_KEY)


def _cached(field, build):
	value = frappe.cache.hget(CACHE_KEY, field)
	if value is None:
		value = build()
		frappe.cache.hset(CACHE_KEY, field, value)
		frappe.cache.expire(CACHE_KEY, CACHE_SECONDS)
	return value


def book_url(book_slug):
	return f"{DOCS_ROUTE}/{book_slug}"


def page_url(book_slug, page_slug):
	return f"{DOCS_ROUTE}/{book_slug}/{page_slug}"


# --- books ----------------------------------------------------------------------------------------


def published_books() -> list[dict]:
	"""Every published book with at least one page to show, grouped later by shelf."""
	return [frappe._dict(b) for b in _cached("books", _load_books)]


def _load_books():
	book = frappe.qb.DocType("Bookstack Book")
	shelf = frappe.qb.DocType("Bookstack Shelf")
	page = frappe.qb.DocType("Bookstack Page")
	pages = (
		frappe.qb.from_(page)
		.select(page.book, frappe.query_builder.functions.Count("*").as_("count"))
		.where(page.html.isnotnull() & (page.html != ""))
		.groupby(page.book)
	).run(as_dict=True)
	page_count = {r.book: r.count for r in pages}

	rows = (
		frappe.qb.from_(book)
		.left_join(shelf).on(shelf.name == book.shelf)
		.select(book.name, book.slug, book.title, book.website_summary, book.description, book.url,
			shelf.title.as_("shelf"))
		.where(book.publish_on_website == 1)
		.orderby(book.title)
	).run(as_dict=True)

	books, seen = [], set()
	for r in rows:
		# A slug can exist on two instances; the URL can only show one of them.
		if not r.slug or r.slug in seen or not page_count.get(r.name):
			continue
		seen.add(r.slug)
		books.append({
			"name": r.name,
			"slug": r.slug,
			"title": r.title or r.slug,
			"summary": (r.website_summary or r.description or "").strip(),
			"shelf": r.shelf,
			"source_url": r.url,
			"url": book_url(r.slug),
			"page_count": page_count[r.name],
		})
	return books


def find_book(slug) -> frappe._dict | None:
	return next((b for b in published_books() if b.slug == slug), None)


def books_by_shelf() -> list[dict]:
	"""[{shelf, books}] in shelf order; books without a shelf come last."""
	groups: dict = {}
	for b in published_books():
		groups.setdefault(b.shelf or "", []).append(b)
	ordered = sorted(groups.items(), key=lambda g: (not g[0], g[0].lower()))
	return [{"shelf": shelf or None, "books": books} for shelf, books in ordered]


# --- contents of one book -------------------------------------------------------------------------


def book_contents(book: frappe._dict) -> list[dict]:
	"""Chapters and loose pages in BookStack's order; chapters keep only pages that are shown.

	[{"type": "chapter", "title", "slug", "description", "pages": [...]}, {"type": "page", ...}]
	"""
	return _cached(f"contents:{book.name}", lambda: _load_contents(book))


def _load_contents(book):
	pages = frappe.get_all(
		"Bookstack Page",
		filters={"book": book.name, "html": ["is", "set"]},
		fields=["name", "slug", "title", "chapter", "priority"],
		order_by="priority asc, title asc",
	)
	chapters = frappe.get_all(
		"Bookstack Chapter",
		filters={"book": book.name},
		fields=["name", "slug", "title", "description", "priority"],
	)

	def entry(p):
		return {"type": "page", "slug": p.slug, "title": p.title or p.slug, "url": page_url(book.slug, p.slug)}

	by_chapter: dict = {}
	entries = []
	for p in pages:
		if not p.slug:
			continue
		if p.chapter:
			by_chapter.setdefault(p.chapter, []).append(entry(p))
		else:
			entries.append((p.priority or 0, entry(p)))
	for c in chapters:
		if by_chapter.get(c.name):
			entries.append((c.priority or 0, {
				"type": "chapter", "slug": c.slug, "title": c.title or c.slug,
				"description": (c.description or "").strip(), "pages": by_chapter[c.name],
			}))
	# BookStack numbers chapters and loose pages of a book in one sequence.
	entries.sort(key=lambda e: e[0])
	return [e for _, e in entries]


def reading_order(contents) -> list[dict]:
	"""All shown pages of a book in reading order, for previous / next."""
	flat = []
	for e in contents:
		flat.extend(e["pages"] if e["type"] == "chapter" else [e])
	return flat


# --- one page -------------------------------------------------------------------------------------


def find_page(book: frappe._dict, page_slug) -> frappe._dict | None:
	page = frappe.db.get_value(
		"Bookstack Page",
		{"book": book.name, "slug": page_slug, "html": ["is", "set"]},
		["name", "slug", "title", "html", "url", "chapter", "updated_at"],
		as_dict=True,
	)
	if not page:
		return None
	page.title = page.title or page.slug
	page.chapter_title = page.chapter and frappe.db.get_value("Bookstack Chapter", page.chapter, "title")
	order = reading_order(book_contents(book))
	index = next((i for i, p in enumerate(order) if p["slug"] == page.slug), None)
	page.previous = order[index - 1] if index else None
	page.next = order[index + 1] if index is not None and index + 1 < len(order) else None
	return page


# --- www pages ------------------------------------------------------------------------------------


def init_page(context, crumbs=()):
	"""Common setup of the three /de/doku pages; only reachable through the route rules in hooks.py."""
	from phamos.web_profile.i18n import set_request_language
	from phamos.web_profile.page import home_crumb

	if frappe.form_dict.get("lang") != "de":
		raise frappe.PageDoesNotExistError
	context.lang = set_request_language("de", context)
	context.wp_docs = 1  # chrome.py: page language for navbar and footer
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.crumbs = [home_crumb(), {"label": frappe._("Documentation"), "url": DOCS_ROUTE}, *crumbs]


def set_page_seo(context, *, title, description, path):
	from phamos.web_profile.page import breadcrumb_schema, set_seo

	set_seo(
		context,
		title=f"{title} · phamos",
		description=description,
		path=path,
		alternates={"de": path},
		schema=[breadcrumb_schema(context.crumbs)],
	)


def describe(html, fallback=""):
	"""Meta description: the first 160 characters of the text.

	A space between elements, so "<h2>Konten</h2><p>1200</p>" reads "Konten 1200", not "Konten1200"."""
	text = " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())
	return (text or fallback)[:160]
