"""The guest web form "event-registration" wrote straight into the attendee table; it is retired.

Custom DocPerm rows (Role Permission Manager) on Attendee are removed as well: they would keep
granting Guest or All access over the permissions defined in attendee.json.
"""

import frappe


def execute():
	frappe.delete_doc("Web Form", "event-registration", ignore_missing=True, force=True)
	if frappe.db.exists("Custom DocPerm", {"parent": "Attendee"}):
		frappe.db.delete("Custom DocPerm", {"parent": "Attendee"})
		frappe.clear_cache(doctype="Attendee")
