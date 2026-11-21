# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Make BookStack page HTML safe and ready for the public website (#2004).

The HTML comes from BookStack's `GET pages/{id}` and is stored on Bookstack Page.html.
It is printed raw on phamos.eu, so everything that could run code or restyle the site
is removed here, before it is stored.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import frappe
from bs4 import BeautifulSoup
from frappe.utils.html_utils import sanitize_html

DOCS_ROUTE = "/de/doku"

# Removed together with their content. bleach would turn them into visible text instead.
_DROP_TAGS = (
	"script", "style", "link", "meta", "iframe", "frame", "object", "embed", "noscript",
	"form", "input", "button", "select", "textarea", "template", "base", "html", "head", "body",
)

_PAGE_PATH = re.compile(r"^/books/(?P<book>[^/]+)(?:/(?P<kind>page|chapter)/(?P<slug>[^/]+))?/?$")
_PERMALINK_PATH = re.compile(r"^/link/(?P<id>\d+)/?$")


def published_link_map(instance: str) -> dict:
	"""Slugs and ids of everything that is shown on the website for one instance."""
	books = frappe.get_all(
		"Bookstack Book",
		filters={"instance": instance, "publish_on_website": 1},
		fields=["name", "slug"],
	)
	slug_by_book = {b.name: b.slug for b in books if b.slug}
	pages = []
	if slug_by_book:
		pages = frappe.get_all(
			"Bookstack Page",
			filters={"instance": instance, "book": ["in", list(slug_by_book)], "draft": 0, "template": 0},
			fields=["bookstack_id", "slug", "book"],
		)
	return {
		"books": set(slug_by_book.values()),
		"pages": {(slug_by_book[p.book], p.slug) for p in pages if p.slug},
		"page_ids": {p.bookstack_id: (slug_by_book[p.book], p.slug) for p in pages if p.slug},
	}


def clean_page_html(html: str, base_url: str, link_map: dict) -> str:
	"""Return BookStack page HTML that is safe to print on phamos.eu."""
	if not html:
		return ""

	soup = BeautifulSoup(html, "html.parser")
	for tag in soup.find_all(_DROP_TAGS):
		tag.decompose()

	safe = sanitize_html(str(soup), always_sanitize=True, disallowed_tags=_DROP_TAGS)

	soup = BeautifulSoup(safe, "html.parser")
	base = base_url.rstrip("/") + "/"
	for a in soup.find_all("a", href=True):
		a["href"] = _rewrite_href(a["href"], base, link_map)
		if not a["href"].startswith(("/", "#")):
			a["rel"] = "noopener"
	for img in soup.find_all("img"):
		if img.get("src"):
			img["src"] = urljoin(base, img["src"])
		img["loading"] = "lazy"
	return str(soup)


def _rewrite_href(href: str, base: str, link_map: dict) -> str:
	"""Point links to published pages at phamos.eu; make the rest absolute."""
	href = href.strip()
	if href.startswith("#") or href.startswith("mailto:"):
		return href

	absolute = urljoin(base, href)
	parts = urlsplit(absolute)
	instance = urlsplit(base)
	if (parts.scheme, parts.netloc) != (instance.scheme, instance.netloc):
		return absolute

	fragment = f"#{parts.fragment}" if parts.fragment else ""
	permalink = _PERMALINK_PATH.match(parts.path)
	if permalink:
		target = link_map["page_ids"].get(int(permalink["id"]))
		return f"{DOCS_ROUTE}/{target[0]}/{target[1]}{fragment}" if target else absolute

	match = _PAGE_PATH.match(parts.path)
	if not match or match["book"] not in link_map["books"]:
		return absolute
	book = match["book"]
	if match["kind"] == "page":
		if (book, match["slug"]) in link_map["pages"]:
			return f"{DOCS_ROUTE}/{book}/{match['slug']}{fragment}"
		return absolute
	if match["kind"] == "chapter":
		return f"{DOCS_ROUTE}/{book}#{match['slug']}"
	return f"{DOCS_ROUTE}/{book}{fragment}"
