# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Website copies of BookStack pages keep their links on BookStack (phamos/phamos#2044).

Until #2044 the sync pointed links at /de/doku/...; the website now does that when it shows a
page, under /de/dokumentation. Copies made before keep /de/doku/... links, which no longer exist:
turn them back into the BookStack URLs they came from. No network: the instance URL is enough.
"""

import re

import frappe

_OLD_LINK = re.compile(r'href="/de/doku/(?P<book>[^/"#]+)(?:/(?P<page>[^/"#]+))?(?:#(?P<fragment>[^"]*))?"')


def bookstack_href(match, base):
	book, page, fragment = match["book"], match["page"], match["fragment"]
	if page:
		url = f"{base}/books/{book}/page/{page}" + (f"#{fragment}" if fragment else "")
	elif fragment:
		url = f"{base}/books/{book}/chapter/{fragment}"  # chapter links became /de/doku/<book>#<chapter>
	else:
		url = f"{base}/books/{book}"
	return f'href="{url}"'


def execute():
	bases = {
		c.name: (c.instance_url or "").rstrip("/")
		for c in frappe.get_all("Bookstack Configuration", fields=["name", "instance_url"])
	}
	for page in frappe.get_all(
		"Bookstack Page", filters={"html": ["like", '%href="/de/doku/%']}, fields=["name", "instance", "html"]
	):
		base = bases.get(page.instance)
		if not base:
			continue
		html = _OLD_LINK.sub(lambda m: bookstack_href(m, base), page.html)
		frappe.db.set_value("Bookstack Page", page.name, "html", html, update_modified=False)
