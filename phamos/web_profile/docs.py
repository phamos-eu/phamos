# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Public documentation under /de/dokumentation and /en/documentation, from BookStack books.

Only books with "Publish on website" are shown, and only their pages whose content the sync has
copied (Bookstack Page.html, phamos/phamos#2004). Nothing is fetched from BookStack per visit.
URLs use BookStack's slugs: /de/dokumentation/<book>/<page> (phamos/phamos#2005, #2044).

The content is German. The English pages show it with English navigation and point search
engines to the German page (canonical) until a translation exists (#2044).

Links inside the copied pages still point to BookStack; render_html points them at the website
when the page is shown, so publishing a book changes links at once, without a sync.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

import frappe
from bs4 import BeautifulSoup

CACHE_KEY = "web_docs"
CACHE_SECONDS = 600
DOCS_ROUTES = {"de": "/de/dokumentation", "en": "/en/documentation"}
DEFAULT_LANGUAGE = "de"


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


def _lang(lang):
	return lang if lang in DOCS_ROUTES else DEFAULT_LANGUAGE


def docs_url(lang, book_slug=None, page_slug=None, anchor=None):
	"""/de/dokumentation[/<book>[/<page>]][#anchor] in ``lang``."""
	url = DOCS_ROUTES[_lang(lang)]
	if book_slug:
		url += f"/{book_slug}"
		if page_slug:
			url += f"/{page_slug}"
	return f"{url}#{anchor}" if anchor else url


def book_url(book_slug, lang=DEFAULT_LANGUAGE):
	return docs_url(lang, book_slug)


def page_url(book_slug, page_slug, lang=DEFAULT_LANGUAGE):
	return docs_url(lang, book_slug, page_slug)


# --- books ----------------------------------------------------------------------------------------


def published_books(lang=DEFAULT_LANGUAGE) -> list[dict]:
	"""Every published book with at least one page to show, with its URL in ``lang``."""
	return [frappe._dict(b, url=book_url(b["slug"], lang)) for b in _cached("books", _load_books)]


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
		.select(book.name, book.instance, book.slug, book.title, book.website_summary, book.description,
			book.url, shelf.title.as_("shelf"))
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
			"instance": r.instance,
			"slug": r.slug,
			"title": r.title or r.slug,
			"summary": (r.website_summary or r.description or "").strip(),
			"shelf": r.shelf,
			"source_url": r.url,
			"source_host": urlsplit(r.url).netloc if r.url else "",
			"page_count": page_count[r.name],
		})
	return books


def find_book(slug, lang=DEFAULT_LANGUAGE) -> frappe._dict | None:
	return next((b for b in published_books(lang) if b.slug == slug), None)


def books_by_shelf(lang=DEFAULT_LANGUAGE) -> list[dict]:
	"""[{shelf, books}] in shelf order; books without a shelf come last."""
	groups: dict = {}
	for b in published_books(lang):
		groups.setdefault(b.shelf or "", []).append(b)
	ordered = sorted(groups.items(), key=lambda g: (not g[0], g[0].lower()))
	return [{"shelf": shelf or None, "books": books} for shelf, books in ordered]


# --- contents of one book -------------------------------------------------------------------------


def book_contents(book: frappe._dict, lang=DEFAULT_LANGUAGE) -> list[dict]:
	"""Chapters and loose pages in BookStack's order; chapters keep only pages that are shown.

	[{"type": "chapter", "title", "slug", "description", "pages": [...]}, {"type": "page", ...}],
	each page with its URL in ``lang``.
	"""
	def with_url(entry):
		return {**entry, "url": page_url(book.slug, entry["slug"], lang)}

	out = []
	for entry in _cached(f"contents:{book.name}", lambda: _load_contents(book)):
		if entry["type"] == "chapter":
			out.append({**entry, "pages": [with_url(p) for p in entry["pages"]]})
		else:
			out.append(with_url(entry))
	return out


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
		return {"type": "page", "slug": p.slug, "title": p.title or p.slug}

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


def find_page(book: frappe._dict, page_slug, lang=DEFAULT_LANGUAGE) -> frappe._dict | None:
	page = frappe.db.get_value(
		"Bookstack Page",
		{"book": book.name, "slug": page_slug, "html": ["is", "set"]},
		["name", "slug", "title", "html", "url", "chapter", "updated_at", "content_updated_at"],
		as_dict=True,
	)
	if not page:
		return None
	page.title = page.title or page.slug
	rendered = render_html(page, lang)
	page.html, page.headings = rendered["html"], rendered["headings"]
	page.chapter_title = page.chapter and frappe.db.get_value("Bookstack Chapter", page.chapter, "title")
	order = reading_order(book_contents(book, lang))
	index = next((i for i, p in enumerate(order) if p["slug"] == page.slug), None)
	page.previous = order[index - 1] if index else None
	page.next = order[index + 1] if index is not None and index + 1 < len(order) else None
	return page


# --- links from the copied pages to the website ---------------------------------------------------

_PAGE_PATH = re.compile(r"^/books/(?P<book>[^/]+)(?:/(?P<kind>page|chapter)/(?P<slug>[^/]+))?/?$")
_PERMALINK_PATH = re.compile(r"^/link/(?P<id>\d+)/?$")
# "erpnext-benutzerhandbuch-v13", "-v13-v15", "-v14" all belong to "erpnext-benutzerhandbuch".
_VERSION_SUFFIX = re.compile(r"(-v\d+)+$")


def _family(book_slug):
	return _VERSION_SUFFIX.sub("", book_slug or "")


def _title_key(title):
	"""Titles compared without case and punctuation: "Kunde (Customer)" == "kunde customer"."""
	return " ".join(re.findall(r"\w+", (title or "").lower()))


def link_index() -> dict:
	"""What the website can show, to point BookStack links at it.

	- hosts: BookStack hosts of the published books
	- books: published book slugs, in title order
	- pages / chapters: {slug: [book slugs]} of what the published books show
	- page_ids: {BookStack page id: (book slug, page slug)} of every page, published or not, so a
	  permalink to an unpublished copy can still be matched by its slug
	- titles: {title key: [(book slug, page slug)]} of the shown pages, and page_titles:
	  {(book slug, page slug): title key} of every page, for copies whose page has another slug
	"""
	return _cached("links", _load_link_index)


def _load_link_index():
	books = _cached("books", _load_books)
	by_name = {b["name"]: b["slug"] for b in books}
	pages: dict = {}
	chapters: dict = {}
	shown = frappe.get_all(
		"Bookstack Page",
		filters={"book": ["in", list(by_name) or [""]], "html": ["is", "set"]},
		fields=["book", "slug", "chapter", "title"],
	)
	titles: dict = {}
	chapter_slugs = dict(frappe.get_all("Bookstack Chapter", filters={"book": ["in", list(by_name) or [""]]},
		fields=["name", "slug"], as_list=True))
	for p in shown:
		book_slug = by_name[p.book]
		if p.slug:
			pages.setdefault(p.slug, []).append(book_slug)
			titles.setdefault(_title_key(p.title), []).append((book_slug, p.slug))
		chapter_slug = chapter_slugs.get(p.chapter)
		if chapter_slug and book_slug not in chapters.get(chapter_slug, []):
			chapters.setdefault(chapter_slug, []).append(book_slug)
	order = {b["slug"]: i for i, b in enumerate(books)}
	for targets in (*pages.values(), *chapters.values()):
		targets.sort(key=order.get)

	all_books = dict(frappe.get_all("Bookstack Book", fields=["name", "slug"], as_list=True))
	all_pages = [
		p for p in frappe.get_all("Bookstack Page", fields=["bookstack_id", "book", "slug", "title"])
		if p.slug and all_books.get(p.book)
	]
	page_ids = {p.bookstack_id: (all_books[p.book], p.slug) for p in all_pages}
	page_titles = {(all_books[p.book], p.slug): _title_key(p.title) for p in all_pages}
	return {
		"hosts": sorted({b["source_host"] for b in books if b["source_host"]}),
		"books": [b["slug"] for b in books],
		"pages": pages,
		"chapters": chapters,
		"page_ids": page_ids,
		"titles": titles,
		"page_titles": page_titles,
	}


def _pick(candidates, origin_book):
	"""The published book to link: the link's own book, else one of its family, else the first."""
	if not candidates:
		return None
	if origin_book in candidates:
		return origin_book
	family = [c for c in candidates if _family(c) == _family(origin_book)]
	return (family or candidates)[0]


def _page_target(book_slug, page_slug, index):
	"""(published book, page slug) for a BookStack page, or None: its own book first, then the same
	slug in a published book, then a shown page with the same title (a copy renamed the slug)."""
	book = _pick(index["pages"].get(page_slug), book_slug)
	if book:
		return book, page_slug
	key = index["page_titles"].get((book_slug, page_slug))
	matches = index["titles"].get(key) if key else None
	if not matches:
		return None
	book = _pick([b for b, _ in matches], book_slug)
	return next(m for m in matches if m[0] == book)


def website_href(href, index, lang=DEFAULT_LANGUAGE):
	"""The website URL for a BookStack link, or None when the website doesn't show its target.

	A page or chapter is found in its own book first, then by slug or title in another published
	book (the published "ERPNext Benutzerhandbuch" links to its older copies v13, v14, v15, #2044).
	A chapter that can't be found opens its book, when the website shows that book or its family.
	"""
	parts = urlsplit(href)
	if parts.netloc not in index["hosts"]:
		return None
	fragment = parts.fragment or None

	permalink = _PERMALINK_PATH.match(parts.path)
	if permalink:
		book_slug, page_slug = index["page_ids"].get(int(permalink["id"]), (None, None))
		target = page_slug and _page_target(book_slug, page_slug, index)
		return docs_url(lang, *target, fragment) if target else None

	match = _PAGE_PATH.match(parts.path)
	if not match:
		return None
	origin = match["book"]
	if match["kind"] == "page":
		target = _page_target(origin, unquote(match["slug"]), index)
		return docs_url(lang, *target, fragment) if target else None
	family_book = _pick([b for b in index["books"] if b == origin or _family(b) == _family(origin)], origin)
	if match["kind"] == "chapter":
		book = _pick(index["chapters"].get(unquote(match["slug"])), origin)
		if book:
			return docs_url(lang, book, anchor=unquote(match["slug"]))
		return docs_url(lang, family_book) if family_book else None  # e.g. a pasted ":~:text=" link
	return docs_url(lang, family_book, anchor=fragment) if family_book else None


def render_html(page, lang=DEFAULT_LANGUAGE) -> dict:
	"""{"html", "headings"} of a page, cached: the stored HTML with links to shown pages pointing at
	the website, every h2 / h3 with an id, and those headings for "On this page" (#2045)."""
	stamp = page.get("content_updated_at") or page.get("updated_at") or ""
	return _cached(f"html:{lang}:{page.name}:{stamp}", lambda: _render(page.html or "", lang))


def _render(html, lang):
	index = link_index()
	soup = BeautifulSoup(html, "html.parser")
	for a in soup.find_all("a", href=True):
		target = website_href(a["href"], index, lang)
		if target:
			a["href"] = target
			if a.get("rel"):
				del a["rel"]  # noopener is for other sites

	headings, used = [], {tag["id"] for tag in soup.find_all(id=True)}
	for n, tag in enumerate(soup.find_all(["h2", "h3"]), 1):
		text = " ".join(tag.get_text(" ").split())
		if not text:
			continue
		if not tag.get("id"):
			# BookStack gives most headings a "bkmrk-" id; the rest get one so they can be jumped to.
			candidate = f"wp-h-{n}"
			while candidate in used:
				candidate += "-x"
			tag["id"] = candidate
			used.add(candidate)
		headings.append({"id": tag["id"], "text": text, "level": int(tag.name[1])})
	return {"html": str(soup), "headings": headings}


# --- www pages ------------------------------------------------------------------------------------


def init_page(context, crumbs=()):
	"""Common setup of the documentation pages; only reachable through the route rules in hooks.py.

	Returns the page language.
	"""
	from phamos.web_profile.i18n import set_request_language
	from phamos.web_profile.page import home_crumb

	lang = frappe.form_dict.get("lang")
	# Frappe would also serve www/documentation/* at /documentation/... with ?lang=de: duplicate
	# pages for search engines.
	request = getattr(frappe.local, "request", None)
	path = "/" + (request.path if request else "").lstrip("/")
	if lang not in DOCS_ROUTES or not (path == DOCS_ROUTES[lang] or path.startswith(DOCS_ROUTES[lang] + "/")):
		raise frappe.PageDoesNotExistError
	context.lang = set_request_language(lang, context)
	context.wp_docs = 1  # chrome.py: page language for navbar and footer
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.docs_home = docs_url(lang)
	context.content_in_other_language = lang != DEFAULT_LANGUAGE
	context.crumbs = [home_crumb(), {"label": frappe._("Documentation"), "url": docs_url(lang)}, *crumbs]
	return lang


def set_page_seo(context, *, title, description, path_for):
	"""``path_for(lang)`` gives the page's path in each language. The German page is canonical:
	the English one shows the same German text until it is translated (#2044)."""
	from phamos.web_profile.page import breadcrumb_schema, set_seo

	alternates = {lang: path_for(lang) for lang in DOCS_ROUTES}
	set_seo(
		context,
		title=f"{title} · phamos",
		description=description,
		path=alternates[context.lang],
		canonical_path=alternates[DEFAULT_LANGUAGE],
		alternates=alternates,
		schema=[breadcrumb_schema(context.crumbs)],
	)


def describe(html, fallback=""):
	"""Meta description: the first 160 characters of the text.

	A space between elements, so "<h2>Konten</h2><p>1200</p>" reads "Konten 1200", not "Konten1200"."""
	text = " ".join(BeautifulSoup(html or "", "html.parser").get_text(" ").split())
	return (text or fallback)[:160]
