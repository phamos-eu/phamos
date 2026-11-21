# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Search in the published documentation only (phamos/phamos#2046).

Books (title, summary) and shown pages (title, plain text in Bookstack Page.search_text) of
books with "Publish on website". Every word of the query must match; title hits rank before
text hits. Used by the results page (www/documentation/search) and the suggestions while typing.

Typos (#2049): a word without an exact hit is also searched as its closest words from the published
documentation ("artikle" → "artikel"); exact hits rank first. ``exact=True`` switches that off.
"""

from __future__ import annotations

import re

import frappe
from frappe.query_builder import Criterion
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html

from phamos.web_profile import docs

MIN_LENGTH = 2
MAX_LENGTH = 100
MAX_WORDS = 6
SNIPPET_CHARS = 90


def search_url(lang, query="", book_slug=None, exact=False):
	from urllib.parse import urlencode

	params = {"q": query} if query else {}
	if book_slug:
		params["book"] = book_slug
	if exact:
		params["exact"] = 1
	return docs.search_path(lang) + (f"?{urlencode(params)}" if params else "")


def words_of(query) -> list[str]:
	"""The query's words, at most MAX_WORDS, each at least MIN_LENGTH characters."""
	query = (query or "").strip()[:MAX_LENGTH]
	return [w for w in query.split() if len(w) >= MIN_LENGTH][:MAX_WORDS]


def _like(word):
	# % and _ typed by a visitor are literal characters, not wildcards.
	return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


# --- typos (#2049) ---------------------------------------------------------------------------------

_WORD = re.compile(r"[^\W\d_]{3,}")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def _norm(word):
	"""Compared without case and with umlauts spelt out: "Mass" == "Maß", "Aenderung" == "Änderung"."""
	return word.lower().translate(_UMLAUTS)


def vocabulary() -> dict:
	"""{normalised word: (word, number of pages)} of the published documentation (cached)."""
	return docs._cached("vocabulary", _load_vocabulary)


def _load_vocabulary():
	books = docs.published_books()
	counts: dict = {}
	rows = frappe.get_all(
		"Bookstack Page",
		filters={"book": ["in", [b.name for b in books] or [""]], "html": ["is", "set"]},
		fields=["title", "search_text"],
	)
	texts = [f"{r.title or ''} {r.search_text or ''}" for r in rows] + [b.title for b in books]
	for text in texts:
		for word in set(w.lower() for w in _WORD.findall(text)):
			counts[word] = counts.get(word, 0) + 1
	vocab: dict = {}
	for word, n in counts.items():
		key = _norm(word)
		if key not in vocab or n > vocab[key][1]:
			vocab[key] = (word, n)
	return vocab


def corrections(word, vocab=None) -> list[str]:
	"""Closest words of the documentation for a word that has no exact hit, most used first.

	A word that appears (also inside a longer word, as the search matches) is not corrected.
	Distance: 1 mistake for words of up to 5 letters, 2 for longer ones; swapped letters count once.
	"""
	from rapidfuzz import process
	from rapidfuzz.distance import DamerauLevenshtein

	vocab = vocabulary() if vocab is None else vocab
	key = _norm(word)
	if len(key) < 3:
		return []
	if key in vocab and vocab[key][0] != word.lower():
		return [vocab[key][0]]  # another spelling of the same word: "aenderung" → "änderung"
	if any(key in candidate for candidate in vocab):
		return []
	allowed = 1 if len(key) <= 5 else 2
	found = process.extract(key, list(vocab), scorer=DamerauLevenshtein.distance, score_cutoff=allowed, limit=12)
	ranked = sorted(found, key=lambda match: (match[1], -vocab[match[0]][1]))
	return [vocab[match[0]][0] for match in ranked[:3]]


def search(query, lang=docs.DEFAULT_LANGUAGE, book_slug=None, limit=30, exact=False) -> dict:
	"""{"books", "pages", "total", "words", "corrected"}: books first, then pages; exact hits and
	title hits first. ``corrected`` is {typed word: [corrections]} for words searched with typos."""
	words = words_of(query)
	books = docs.published_books(lang)
	if book_slug:
		books = [b for b in books if b.slug == book_slug]
	if not words or not books:
		return {"books": [], "pages": [], "words": words, "corrected": {}}

	vocab = None if exact else vocabulary()
	corrected = {}
	if not exact:
		for w in words:
			found = corrections(w, vocab)
			if found:
				corrected[w] = found
	variants = {w: [w, *corrected.get(w, [])] for w in words}

	def matches(text, strict=False):
		text = (text or "").lower()
		if strict:
			return all(w.lower() in text for w in words)
		return all(any(v.lower() in text for v in variants[w]) for w in words)

	book_hits = [] if book_slug else [b for b in books if matches(f"{b.title} {b.summary}")]

	by_name = {b.name: b for b in books}
	page = frappe.qb.DocType("Bookstack Page")
	chapter = frappe.qb.DocType("Bookstack Chapter")
	per_word = [
		Criterion.any([page.title.like(_like(v)) | page.search_text.like(_like(v)) for v in variants[w]])
		for w in words
	]
	rows = (
		frappe.qb.from_(page)
		.left_join(chapter).on(chapter.name == page.chapter)
		.select(page.name, page.slug, page.title, page.book, page.search_text, chapter.title.as_("chapter_title"))
		.where(page.book.isin(list(by_name)))
		.where(page.html.isnotnull() & (page.html != ""))
		.where(Criterion.all(per_word))
		.limit(200)
	).run(as_dict=True)

	every_variant = [v for w in words for v in variants[w]]
	pages = []
	for r in rows:
		book = by_name[r.book]
		pages.append({
			"title": r.title or r.slug,
			"url": docs.page_url(book.slug, r.slug, lang),
			"book_title": book.title,
			"chapter_title": r.chapter_title,
			"snippet": snippet(r.search_text, every_variant),
			"in_title": matches(r.title),
			"exact": matches(f"{r.title} {r.search_text}", strict=True),
		})
	pages.sort(key=lambda p: (not p["exact"], not p["in_title"], p["title"].lower()))
	return {"books": book_hits, "pages": pages[:limit], "total": len(pages), "words": words, "corrected": corrected}


def corrected_query(query, corrected) -> str:
	"""The query with every corrected word replaced by its best correction, for the note."""
	return " ".join(corrected[w][0] if w in corrected else w for w in (query or "").split())


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
