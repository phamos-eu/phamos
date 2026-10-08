"""Every Stakeholder Web Profile gets its anonymous route at creation (phamos/phamos#1508), so the
URL exists before the profile is ever anonymous. Profiles whose anonymous page is already public
are flagged, so their anonymous URL redirects to the named page after a switch to Named.
"""

import frappe


def execute():
	for name in frappe.get_all("Stakeholder Web Profile", filters={"anonymous_route": ["is", "not set"]}, pluck="name"):
		doc = frappe.get_doc("Stakeholder Web Profile", name)
		doc.set_anonymous_route()
		doc.db_set("anonymous_route", doc.anonymous_route, update_modified=False)
	frappe.db.sql("update `tabStakeholder Web Profile` set anonymous_route_published = 1"
		" where published = 1 and publish_as = 'Anonymous'")
