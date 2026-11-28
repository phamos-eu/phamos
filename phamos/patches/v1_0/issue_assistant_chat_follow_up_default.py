"""Issue Assistant Settings: store the default of "Follow-up window (minutes)" (#2231).

A field added to a saved Single has no tabSingles row and an Int reads 0 (#1842), which would switch the
follow-up off. Stores 10 only where no row exists; checked with raw SQL (tabSingles has no name column).
"""

import frappe

SETTINGS = "Issue Assistant Settings"


def execute():
	if not frappe.db.sql("select 1 from `tabSingles` where doctype=%s and field=%s", (SETTINGS, "chat_follow_up_minutes")):
		frappe.db.sql("insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)",
			(SETTINGS, "chat_follow_up_minutes", 10))
	frappe.clear_document_cache(SETTINGS, SETTINGS)
