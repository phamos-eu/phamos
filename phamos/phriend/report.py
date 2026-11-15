# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The Phriend report of an Issue, as the cockpit Issue page shows it (#1901)."""

import json
import re
from urllib.parse import quote, urlparse

import frappe
from frappe.utils import cstr

# The reporter's browser filled the context, so the payload takes only known keys, in known shapes,
# and caps the lists (the browser keeps at most 20 of each anyway).
MAX_ENTRIES = 20
MAX_TEXT = 300
ENTRY_KEYS = ("at", "type", "message", "source", "url", "method", "status")


def issue_report(doc):
	"""{type, reporter, screenshot, page, record, details} for an Issue Phriend created, else None.

	The caller has checked that the user may read the Issue; nothing here needs more than that.
	The reporter's comment is not repeated: it is in the Issue description.
	"""
	if not doc.get("phriend_type"):
		return None
	context = _context(doc.get("phriend_context"))
	return {
		"type": doc.phriend_type,
		"reported_by": doc.get("phriend_reported_by"),
		"reported_by_name": doc.get("phriend_reported_by_name") or doc.get("phriend_reported_by"),
		"reported_at": doc.creation,
		"screenshot": doc.get("phriend_screenshot") or None,
		"route": doc.get("phriend_route") or "",
		"page_url": _web_url(doc.get("phriend_page_url")),
		"ref_doctype": doc.get("phriend_ref_doctype") or None,
		"ref_docname": doc.get("phriend_ref_docname") or None,
		"ref_url": _desk_url(doc.get("phriend_ref_doctype"), doc.get("phriend_ref_docname")),
		"details": context,
	}


def _context(raw):
	"""The captured context, reduced to what the details show."""
	try:
		ctx = json.loads(raw) if isinstance(raw, str) and raw else (raw or {})
	except ValueError:
		ctx = {}
	if not isinstance(ctx, dict):
		ctx = {}
	versions = ctx.get("versions")
	return {
		"app": _text(ctx.get("app")),
		"captured_at": _text(ctx.get("captured_at")),
		"lang": _text(ctx.get("lang")),
		"viewport": _text(ctx.get("viewport")),
		# reports from before the GDPR review of !1162 carry the full user agent instead
		"browser": _text(ctx.get("browser")) or _browser_name(cstr(ctx.get("user_agent"))),
		"versions": {_text(k): _text(v) for k, v in versions.items()} if isinstance(versions, dict) else {},
		"recent_errors": _entries(ctx.get("recent_errors")),
		"failed_requests": _entries(ctx.get("failed_requests")),
	}


def _entries(items):
	if not isinstance(items, list):
		return []
	entries = []
	for item in items[-MAX_ENTRIES:]:
		if isinstance(item, dict):
			entries.append({k: _text(item[k]) for k in ENTRY_KEYS if item.get(k) not in (None, "")})
		elif item:
			entries.append({"message": _text(item)})
	return entries


def _browser_name(ua):
	"""'Chrome 156, macOS' from a user agent, as the browser sends it today (util.js browser_name)."""
	if not ua:
		return ""
	match = re.search(r"(Edg|OPR|Firefox|Chrome|Version)/(\d+)", ua) or re.search(r"(Safari)/(\d+)", ua)
	names = {"Edg": "Edge", "OPR": "Opera", "Version": "Safari"}
	systems = (("Mac OS X", "macOS"), ("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iOS"),
		("iPad", "iOS"), ("Linux", "Linux"))
	system = next((name for marker, name in systems if marker in ua), "")
	browser = f"{names.get(match.group(1), match.group(1))} {match.group(2)}" if match else ""
	return ", ".join(part for part in (browser, system) if part)


def _text(value):
	return cstr(value)[:MAX_TEXT] if value is not None else ""


def _web_url(url):
	"""The page the report came from, only as an http(s) link: the browser sent it."""
	url = cstr(url).strip()
	return url if urlparse(url).scheme in ("http", "https") else None


def _desk_url(doctype, name):
	if not (doctype and name):
		return None
	return f"/app/{frappe.scrub(doctype).replace('_', '-')}/{quote(cstr(name), safe='')}"
