"""Give every cockpit its logo colour, glow "Off", the glow edges right and bottom and breathing on
in Cockpit Settings (phamos/phamos#1933).

New fields on a Single that sites already saved have no stored value and read as empty, which
would mean "no colour". Values someone already set stay. Safe to run twice.
"""

import frappe

from phamos.cockpits.settings import COCKPIT_SETTINGS, COCKPITS, DEFAULT_GLOW_EDGES, GLOW_EDGES, GLOW_OFF


def execute():
	frappe.reload_doc("cockpits", "doctype", "cockpit_settings")
	for prefix, color in COCKPITS.values():
		_store_default(f"{prefix}_color", color)
		_store_default(f"{prefix}_glow", GLOW_OFF)
		for edge in GLOW_EDGES:
			_store_default(f"{prefix}_glow_{edge}", int(edge in DEFAULT_GLOW_EDGES))
		_store_default(f"{prefix}_glow_breathing", 1)


def _store_default(field, value):
	# tabSingles has no `name` column, so frappe.db.exists can't tell; ask the table directly.
	if frappe.db.sql(
		"select 1 from `tabSingles` where doctype = %s and field = %s", (COCKPIT_SETTINGS, field)
	):
		return
	frappe.db.set_single_value(COCKPIT_SETTINGS, field, value, update_modified=False)
