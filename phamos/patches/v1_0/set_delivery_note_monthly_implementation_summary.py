"""Fill the new Monthly Implementation Summary field on Delivery Notes the MIS created earlier.

The field sits in the "phamos" section at the top of the Delivery Note. Until now the link was only on
the lines (``custom_against_monthly_implementation_summary``) and in the MIS's own Delivery Notes table.
The line link wins; without it, the MIS Delivery Notes row of a MIS that is not cancelled is used.
Values already set are kept. Running it again changes nothing.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field


def execute():
	# migrate syncs the fixture only after the patches
	if not frappe.db.has_column("Delivery Note", "custom_monthly_implementation_summary"):
		create_custom_field("Delivery Note", {
			"fieldname": "custom_monthly_implementation_summary",
			"label": "Monthly Implementation Summary",
			"fieldtype": "Link",
			"options": "Monthly Implementation Summary",
			"insert_after": "custom_implementation",
			"read_only": 1,
			"no_copy": 1,
		})

	# The MIS Delivery Note table is removed by mis_links_from_documents (#1987); without it, only the line link
	if not frappe.db.table_exists("MIS Delivery Note"):
		_fill_from_lines()
		return

	rows = frappe.db.sql("""
		select dn.name,
			(select dni.custom_against_monthly_implementation_summary from `tabDelivery Note Item` dni
				where dni.parent = dn.name and ifnull(dni.custom_against_monthly_implementation_summary, '') != ''
				order by dni.idx limit 1) as from_item,
			(select mdn.parent from `tabMIS Delivery Note` mdn
				join `tabMonthly Implementation Summary` mis on mis.name = mdn.parent and mis.docstatus != 2
				where mdn.delivery_note = dn.name order by mis.creation limit 1) as from_mis
		from `tabDelivery Note` dn
		where ifnull(dn.custom_monthly_implementation_summary, '') = ''
	""", as_dict=True)
	filled = 0
	for row in rows:
		mis = row.from_item or row.from_mis
		if mis and frappe.db.exists("Monthly Implementation Summary", mis):
			frappe.db.set_value("Delivery Note", row.name, "custom_monthly_implementation_summary", mis,
				update_modified=False)
			filled += 1
	if filled:
		print(f"Set the Monthly Implementation Summary on {filled} Delivery Note(s)")


def _fill_from_lines():
	frappe.db.sql("""
		update `tabDelivery Note` dn
		join (
			select dni.parent, min(dni.custom_against_monthly_implementation_summary) as mis
			from `tabDelivery Note Item` dni
			where dni.parenttype = 'Delivery Note'
				and ifnull(dni.custom_against_monthly_implementation_summary, '') != ''
			group by dni.parent
		) l on l.parent = dn.name
		join `tabMonthly Implementation Summary` m on m.name = l.mis
		set dn.custom_monthly_implementation_summary = l.mis
		where ifnull(dn.custom_monthly_implementation_summary, '') = ''
	""")
