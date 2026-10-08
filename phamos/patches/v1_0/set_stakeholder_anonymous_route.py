"""Anonymous Stakeholder Web Profiles get a stored, readable URL slug (phamos/phamos#1507).

Generated like on save: German text title, else industry + region, else the stakeholder type.
Named profiles get theirs when they are switched to Anonymous.
"""

import frappe


def execute():
	for name in frappe.get_all("Stakeholder Web Profile",
			filters={"publish_as": "Anonymous", "anonymous_route": ["is", "not set"]}, pluck="name"):
		doc = frappe.get_doc("Stakeholder Web Profile", name)
		doc.set_anonymous_route()
		doc.db_set("anonymous_route", doc.anonymous_route, update_modified=False)
