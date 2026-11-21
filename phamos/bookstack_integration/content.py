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
from bleach.css_sanitizer import CSSSanitizer
from bs4 import BeautifulSoup, Comment
from frappe.utils.html_utils import sanitize_html

# Attributes that make the browser fetch something; checked against the BookStack host.
_URL_ATTRS = ("src", "poster", "background", "href", "xlink:href", "data")
_MEDIA_TAGS = ("img", "video", "audio", "source")

# Removed together with their content. bleach would turn them into visible text instead.
_DROP_TAGS = (
	"script", "style", "link", "meta", "iframe", "frame", "object", "embed", "noscript",
	"form", "input", "button", "select", "textarea", "template", "base", "html", "head", "body",
	# bleach would print these as visible "<track …>" text; none has a use on the website
	"track", "picture", "image", "applet", "portal",
)

# Inline styles BookStack's editor writes (alignment, colours, table sizes). Frappe's own list also
# allows position, z-index, display and the like, which would let a wiki page cover phamos.eu.
_SAFE_CSS = CSSSanitizer(allowed_css_properties=[
	"text-align", "vertical-align", "color", "background-color", "font-weight", "font-style",
	"text-decoration", "width", "height", "min-width", "max-width", "border", "border-color",
	"border-width", "border-style", "border-collapse", "padding", "margin-left", "list-style-type",
	"white-space",
])

# Classes BookStack's editor sets that the website styles. Any other class could borrow phamos.eu's
# own (a stretched link, a fixed overlay) and cover the page, so it is dropped (review S6).
_SAFE_CLASSES = {"callout", "info", "success", "warning", "danger", "align-left", "align-center",
	"align-right", "align-justify"}
_SAFE_CLASS_PREFIXES = ("language-",)  # code blocks
# BookStack's heading anchors; other ids could clobber the website's scripts.
_SAFE_ID = re.compile(r"^bkmrk-[\w-]*$")
# Attributes bleach keeps that a copied page has no use for: "ping" makes the visitor's browser
# post to any host on click, "name" clobbers DOM globals.
_DROP_ATTRS = ("ping", "name")

def clean_page_html(html: str, base_url: str) -> str:
	"""Return BookStack page HTML that is safe to print on phamos.eu.

	Links are made absolute but stay on BookStack: the website points them at its own pages when it
	shows the page (phamos.web_profile.docs.render_html, #2044), so publishing a book changes links
	without fetching every page again.
	"""
	if not html:
		return ""

	soup = BeautifulSoup(html, "html.parser")
	for tag in soup.find_all(_DROP_TAGS):
		tag.decompose()

	safe = sanitize_html(str(soup), always_sanitize=True, disallowed_tags=_DROP_TAGS)

	soup = BeautifulSoup(safe, "html.parser")
	# Comments are published verbatim otherwise: internal notes, and a surface for parser tricks.
	for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
		comment.extract()
	for tag in soup.find_all(True):
		for attr in [a for a in tag.attrs if a.startswith("data-") or a in _DROP_ATTRS]:
			del tag[attr]
		if tag.get("style"):
			tag["style"] = _SAFE_CSS.sanitize_css(tag["style"])
			if not tag["style"].strip():
				del tag["style"]
		if tag.get("class"):
			classes = tag["class"] if isinstance(tag["class"], list) else tag["class"].split()
			keep = [c for c in classes if c in _SAFE_CLASSES or c.startswith(_SAFE_CLASS_PREFIXES)]
			if keep:
				tag["class"] = keep
			else:
				del tag["class"]
		if tag.get("id") and not _SAFE_ID.match(tag["id"]):
			del tag["id"]

	base = base_url.rstrip("/") + "/"
	instance_host = urlsplit(base).netloc
	for a in soup.find_all("a", href=True):
		a["href"] = _absolute_href(a["href"], base)
		if not a["href"].startswith(("/", "#")):
			rel = a.get("rel") or []
			a["rel"] = sorted({*(rel if isinstance(rel, list) else rel.split()), "noopener"})
	# Only media from the BookStack host: any other host would learn every visitor's IP address
	# (privacy, decided 2026-11-21). This covers every URL attribute the cleaning keeps, not only
	# <img src>: <video src/poster>, <audio>, <source>, <table background>. Copying media to
	# phamos.eu comes later.
	def own_host(value):
		url = urljoin(base, value.strip())
		parts = urlsplit(url)
		return url if parts.netloc == instance_host and parts.scheme in ("http", "https") else None

	for tag in soup.find_all(True):
		if tag.name == "a" or tag.decomposed:
			continue
		tag.attrs.pop("srcset", None)  # several URLs in one value; the plain src is enough
		for attr in _URL_ATTRS:
			if attr not in tag.attrs:
				continue
			value = tag[attr] if isinstance(tag[attr], str) else " ".join(tag[attr])
			url = own_host(value) if value.strip() else None  # urljoin turns "" into the start page
			if url:
				tag[attr] = url
			elif tag.name in _MEDIA_TAGS and attr == "src":
				tag.decompose()  # nothing to show without its source
				break
			else:
				del tag[attr]
	for media in soup.find_all(_MEDIA_TAGS):
		if not media.decomposed and not media.get("src") and not media.find("source"):
			media.decompose()  # an <img> or <video> left without any source
	for img in soup.find_all("img"):
		img["loading"] = "lazy"
	return str(soup)


def _absolute_href(href: str, base: str) -> str:
	"""Anchors and mail links as they are; everything else absolute to the BookStack instance."""
	href = href.strip()
	if href.startswith("#") or href.startswith("mailto:"):
		return href
	return urljoin(base, href)
