"""Marketing Event Registration becomes Attendee (module Marketing).

Runs before the model sync so the existing table and records are renamed, not recreated. Only
``frappe.db`` and ``rename_doc`` are used: the controllers moved to ``phamos.marketing`` and the
database still says module "Phamos" at this point.
"""

import frappe


def execute():
	if frappe.db.exists("DocType", "Attendee"):
		return
	if frappe.db.exists("DocType", "Marketing Event Registration"):
		frappe.rename_doc("DocType", "Marketing Event Registration", "Attendee", force=True)
