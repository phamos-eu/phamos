"""The MIS no longer links to its Delivery Notes and Sales Invoices; they point at the MIS (phamos/phamos#1987).

A link from a submitted MIS to a Delivery Note or Sales Invoice blocked cancelling it. In order:
1. Sales Invoice: fill the new ``custom_monthly_implementation_summary`` from the MIS Sales Invoice rows.
2. Delivery Note: fill ``custom_monthly_implementation_summary`` where still empty, from the line link or
   the MIS Delivery Note rows (as ``set_delivery_note_monthly_implementation_summary`` did).
3. Delete the child DocTypes MIS Delivery Note and MIS Sales Invoice with their rows.

Only MIS that are not cancelled count; the oldest wins. Values already set are kept. Running it again
changes nothing.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

FIELD = "custom_monthly_implementation_summary"


def execute():
	# migrate syncs the fixture only after the patches
	if not frappe.db.has_column("Sales Invoice", FIELD):
		create_custom_field("Sales Invoice", {
			"fieldname": FIELD,
			"label": "Monthly Implementation Summary",
			"fieldtype": "Link",
			"options": "Monthly Implementation Summary",
			"insert_after": "custom_implementation",
			"read_only": 1,
			"no_copy": 1,
			"search_index": 1,
		})

	if frappe.db.table_exists("MIS Sales Invoice"):
		_fill("Sales Invoice", "MIS Sales Invoice", "sales_invoice")

	from phamos.patches.v1_0 import set_delivery_note_monthly_implementation_summary
	set_delivery_note_monthly_implementation_summary.execute()

	for doctype in ("MIS Delivery Note", "MIS Sales Invoice"):
		if frappe.db.exists("DocType", doctype):
			frappe.delete_doc("DocType", doctype, force=True, ignore_permissions=True)
		frappe.db.sql_ddl(f"drop table if exists `tab{doctype}`")


def _fill(doctype, child_doctype, link_field):
	first_mis = {}
	for row in frappe.db.sql(f"""
		select c.{link_field} as target, c.parent as mis
		from `tab{child_doctype}` c
		join `tabMonthly Implementation Summary` mis on mis.name = c.parent and mis.docstatus != 2
		where ifnull(c.{link_field}, '') != ''
		order by mis.creation, c.idx
	""", as_dict=True):
		first_mis.setdefault(row.target, row.mis)
	filled = 0
	for target, mis in first_mis.items():
		current = frappe.db.get_value(doctype, target, ["name", FIELD], as_dict=True)
		if not current or current.get(FIELD):  # gone, or already set
			continue
		frappe.db.set_value(doctype, target, FIELD, mis, update_modified=False)
		filled += 1
	if filled:
		print(f"Set the Monthly Implementation Summary on {filled} {doctype}(s)")
