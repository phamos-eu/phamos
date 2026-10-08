"""Person Web Profiles: no full names in URLs, and two URLs fixed at creation (phamos/phamos#1509).

- Named routes that contain the surname become first name + initial ("wolfram-schmidt" -> "wolfram-s").
- Every profile gets its random anonymous route.
- Profiles that are already shown anonymously are flagged, so their anonymous URL redirects to the
  named page should they be named later.
Old public URLs are mapped with Website Route Redirect records at go-live (phamos/phamos#1487).
"""

import frappe


def execute():
	for name in frappe.get_all("Person Web Profile", pluck="name"):
		doc = frappe.get_doc("Person Web Profile", name)
		values = {}
		surname = doc.surname_slug()
		if not doc.route or (surname and f"-{surname}-" in f"-{doc.route}-"):
			doc.route = None
			doc.set_route()
			values["route"] = doc.route
		if not doc.anonymous_route or (doc.published and not doc.shown_named() and not doc.anonymous_route_published):
			doc.set_anonymous_route()
			values.update(anonymous_route=doc.anonymous_route, anonymous_route_published=doc.anonymous_route_published)
		if values:
			doc.db_set(values, update_modified=False)
