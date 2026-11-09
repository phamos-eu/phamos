"""Show the author of ideas handed in for a vote by default (phamos/phamos#1842).

A Check added to a Single that was saved before has no stored value, and Frappe reads that as
0. The agreed default is on, so existing sites get 1 unless someone already chose a value.
"""

import frappe

SETTINGS = "phamos Settings"
FIELD = "personal_ideas_show_author"


def execute():
	"""Store 1 for the switch when phamos Settings has no value for it yet. Safe to run twice."""
	# tabSingles has no `name` column, so frappe.db.exists can't tell; ask the table directly.
	stored = frappe.db.sql("select 1 from `tabSingles` where doctype = %s and field = %s", (SETTINGS, FIELD))
	if stored:
		return
	frappe.db.set_single_value(SETTINGS, FIELD, 1)
