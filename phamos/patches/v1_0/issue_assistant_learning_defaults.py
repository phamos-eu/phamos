"""Issue Assistant Settings: store the defaults of the two Learning fields (#2225).

A field added to a Single that sites already saved has no row in tabSingles, and an Int then reads 0
instead of its default (#1842). Stores 7 and 90 only where no row exists, so a chosen value stays.
Checked with raw SQL: tabSingles has no name column, so frappe.db.exists can't tell.
"""

import frappe

SETTINGS = "Issue Assistant Settings"
DEFAULTS = {"accept_after_days": 7, "stats_window_days": 90}


def execute():
	for field, value in DEFAULTS.items():
		if not frappe.db.sql("select 1 from `tabSingles` where doctype=%s and field=%s", (SETTINGS, field)):
			frappe.db.sql("insert into `tabSingles` (doctype, field, value) values (%s, %s, %s)", (SETTINGS, field, value))
	frappe.clear_document_cache(SETTINGS, SETTINGS)
