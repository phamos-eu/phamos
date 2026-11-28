"""Take back the rights the "Event Ticketing" role no longer needs (phamos/phamos#1708, finding #1586).

Before #1708 the role had read on 13 core doctypes. Granting it copied each doctype's standard permissions into
Custom DocPerm, so these doctypes stopped following ERPNext's permission updates. A website order needs only
Item read and Account select (``phamos.marketing.setup``). For every other doctype this patch:
- deletes the role's Custom DocPerm rows;
- if the remaining Custom DocPerm rows are an untouched copy of the standard ones, deletes them too, so the
  doctype follows the standard again. A copy someone changed in Role Permission Manager is kept.

Prints per doctype what it removed and kept. Running it again changes nothing.
"""

import frappe

from phamos.marketing.setup import FORMER_TICKETING_DOCTYPES, TICKETING_ROLE, custom_perms_match_standard


def execute():
	for doctype in FORMER_TICKETING_DOCTYPES:
		if not frappe.db.exists("DocType", doctype):
			continue
		own = frappe.db.count("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE})
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE})
		rest = frappe.db.count("Custom DocPerm", {"parent": doctype})
		if rest and custom_perms_match_standard(doctype):
			frappe.db.delete("Custom DocPerm", {"parent": doctype})
			print(f"{doctype}: removed {own} Event Ticketing row(s) and the untouched copy ({rest} rows); "
				"standard permissions apply again")
		elif rest:
			print(f"{doctype}: removed {own} Event Ticketing row(s); kept {rest} customised row(s)")
		elif own:
			print(f"{doctype}: removed {own} Event Ticketing row(s)")
		frappe.clear_cache(doctype=doctype)
