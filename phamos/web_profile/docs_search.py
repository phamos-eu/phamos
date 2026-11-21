# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Search in the published documentation only (phamos/phamos#2046).

Books (title, summary) and shown pages (title, plain text in Bookstack Page.search_text) of
books with "Publish on website". Every word of the query must match; title hits rank before
text hits. Used by the results page (www/documentation/search) and the suggestions while typing.
"""

from __future__ import annotations

import re

import frappe
from frappe.query_builder import Case, Criterion
from frappe.query_builder.functions import Count
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html

from phamos.web_profile import docs

MIN_LENGTH = 2
MAX_LENGTH = 100
MAX_WORDS = 6
SNIPPET_CHARS = 90
ROW_LIMIT = 200  # pages read per search; the count and the order don't depend on it


def search_url(lang, query="", book_slug=None):
	from urllib.parse import urlencode

	params = {"q": query} if query else {}
	if book_slug:
		params["book"] = book_slug
	return docs.search_path(lang) + (f"?{urlencode(params)}" if params else "")


def words_of(query) -> list[str]:
	"""The query's words, at most MAX_WORDS, each at least MIN_LENGTH characters."""
	query = (query or "").strip()[:MAX_LENGTH]
	return [w for w in query.split() if len(w) >= MIN_LENGTH][:MAX_WORDS]


def _like(word):
	# % and _ typed by a visitor are literal characters, not wildcards.
	return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def search(query, lang=docs.DEFAULT_LANGUAGE, book_slug=None, limit=30) -> dict:
	"""{"books": [...], "pages": [...], "words": [...]}: books first, then pages, title hits first."""
	words = words_of(query)
	books = docs.published_books(lang)
	if book_slug:
		books = [b for b in books if b.slug == book_slug]
	if not words or not books:
		return {"books": [], "pages": [], "words": words}

	def matches(text):
		text = (text or "").lower()
		return all(w.lower() in text for w in words)

	book_hits = [] if book_slug else [b for b in books if matches(f"{b.title} {b.summary}")]

	by_name = {b.name: b for b in books}
	page = frappe.qb.DocType("Bookstack Page")
	chapter = frappe.qb.DocType("Bookstack Chapter")
	found = Criterion.all([
		page.book.isin(list(by_name)),
		page.html.isnotnull() & (page.html != ""),
		*[page.title.like(_like(w)) | page.search_text.like(_like(w)) for w in words],
	])
	# Counted on their own and ordered in the database: the list is cut at 200 rows, and both the
	# count and the title hits must not depend on which 200 came back (review of !1291).
	total = frappe.qb.from_(page).select(Count("*")).where(found).run()[0][0]
	title_first = Case().when(Criterion.all([page.title.like(_like(w)) for w in words]), 0).else_(1)
	rows = (
		frappe.qb.from_(page)
		.left_join(chapter).on(chapter.name == page.chapter)
		.select(page.name, page.slug, page.title, page.book, page.search_text, chapter.title.as_("chapter_title"))
		.where(found)
		.orderby(title_first)
		.orderby(page.title)
		.limit(ROW_LIMIT)
	).run(as_dict=True)

	pages = []
	for r in rows:
		book = by_name[r.book]
		in_title = matches(r.title)
		pages.append({
			"title": r.title or r.slug,
			"url": docs.page_url(book.slug, r.slug, lang),
			"book_title": book.title,
			"chapter_title": r.chapter_title,
			"snippet": snippet(r.search_text, words),
			"in_title": in_title,
		})
	pages.sort(key=lambda p: (not p["in_title"], p["title"].lower()))
	return {"books": book_hits, "pages": pages[:limit], "total": total, "words": words}


def snippet(text, words) -> str:
	"""HTML: a short piece of ``text`` around the first match, matches in <mark>, all else escaped."""
	text = text or ""
	lower = text.lower()
	positions = [lower.find(w.lower()) for w in words if lower.find(w.lower()) >= 0]
	if not positions:
		piece = text[: SNIPPET_CHARS * 2]
		return escape_html(piece) + ("…" if len(text) > len(piece) else "")
	start = max(0, min(positions) - SNIPPET_CHARS)
	end = min(len(text), min(positions) + SNIPPET_CHARS)
	# whole words at both ends ("…Entscheidungen", not "…cheidungen")
	if start:
		space = text.find(" ", start, min(positions))
		start = space + 1 if space >= 0 else start
	if end < len(text):
		space = text.rfind(" ", min(positions), end)
		end = space if space > min(positions) else end
	piece = text[start:end]
	# Matched on the raw text and escaped piece by piece, so a <mark> never lands inside an entity
	# (a search for "am" must not split "&amp;").
	pattern = re.compile("|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)), re.IGNORECASE)
	out, last = [], 0
	for m in pattern.finditer(piece):
		out += [escape_html(piece[last:m.start()]), f"<mark>{escape_html(m.group(0))}</mark>"]
		last = m.end()
	out.append(escape_html(piece[last:]))
	return ("…" if start else "") + "".join(out) + ("…" if end < len(text) else "")


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=120, seconds=60)
def suggest(q=None, book=None, lang=None):
	"""Up to 8 suggestions while typing: book and page titles with their URL (no snippets)."""
	lang = docs._lang(lang)
	result = search(q, lang, book_slug=book or None, limit=8)
	out = [{"title": b.title, "subtitle": frappe._("Book"), "url": b.url} for b in result["books"][:3]]
	for p in result["pages"]:
		out.append({"title": p["title"], "subtitle": " · ".join(x for x in (p["book_title"], p["chapter_title"]) if x),
			"url": p["url"]})
	return out[:8]
