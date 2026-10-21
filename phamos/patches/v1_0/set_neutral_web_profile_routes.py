"""One neutral URL per Web Profile, set once and never rewritten (phamos/phamos#1512).

Person Web Profiles get a random code, Stakeholder Web Profiles a neutral slug and Implementation
Web Profiles industry + start year. A neutral anonymous route that already exists (#1507–#1509) is
kept as the one URL. Runs before any profile is live, so no public URL changes.
"""

import frappe

DOCTYPES = ("Person Web Profile", "Stakeholder Web Profile", "Implementation Web Profile")


def execute():
	for doctype in DOCTYPES:
		columns = set(frappe.db.get_table_columns(doctype))
		keep = {}
		if "anonymous_route" in columns:
			keep = dict(frappe.db.sql(f"select name, anonymous_route from `tab{doctype}` where ifnull(anonymous_route, '') != ''"))
		# Free all routes first, so the new ones can't collide with an old one of another record.
		frappe.db.sql(f"update `tab{doctype}` set route = null")
		for name in frappe.get_all(doctype, pluck="name", order_by="creation asc"):
			doc = frappe.get_doc(doctype, name)
			doc.route = keep.get(name)
			doc.set_route()
			frappe.db.set_value(doctype, name, "route", doc.route, update_modified=False)
