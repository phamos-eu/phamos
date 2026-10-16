"""Events move to the Web Profile engine (/de/veranstaltungen, /en/events).

- ``legacy_route`` keeps the old route (``events/<x>`` or a bare slug) for the go-live redirects;
- ``route`` becomes the bare slug of the old route, unique among events;
- the old English texts (intro, description) become an "en" row of the "Web Profile Content" table.

Idempotent: records that already have a ``legacy_route`` or an "en" text row are skipped for that step.
"""

import frappe

from phamos.web_profile.utils import slugify


def execute():
	records = frappe.db.sql("select name, title, route, legacy_route, intro, description from `tabMarketing Content`",
		as_dict=True)
	taken = {r.route for r in records if r.legacy_route and r.route}
	new_routes = {}
	for r in records:
		if r.legacy_route:
			continue
		old = (r.route or "").strip("/")
		base = slugify(old.removeprefix("events/")) or slugify(r.title) or slugify(r.name)
		route, counter = base, 2
		while route in taken:
			route, counter = f"{base}-{counter}", counter + 1
		taken.add(route)
		new_routes[r.name] = (old or None, route)
	# Two passes: "route" is unique, and a new slug may equal another record's old route.
	for name in new_routes:
		frappe.db.set_value("Marketing Content", name, "route", f"tmp-{frappe.generate_hash(length=12)}",
			update_modified=False)
	for name, (old, route) in new_routes.items():
		frappe.db.set_value("Marketing Content", name, {"legacy_route": old, "route": route}, update_modified=False)
	for r in records:
		if (r.intro or r.description) and not frappe.db.exists("Web Profile Content",
				{"parenttype": "Marketing Content", "parent": r.name, "language": "en"}):
			idx = frappe.db.count("Web Profile Content", {"parenttype": "Marketing Content", "parent": r.name})
			frappe.get_doc({
				"doctype": "Web Profile Content", "parent": r.name, "parenttype": "Marketing Content",
				"parentfield": "translations", "idx": idx + 1, "language": "en", "title": r.title,
				"summary": r.intro, "content": r.description,
			}).db_insert()
	frappe.cache.delete_value("web_profile_items")
