import frappe


def execute():
	for fieldname in ("total_hrs", "delivered_total_hrs", "remaining_hrs"):
		frappe.db.set_value(
			"DocField",
			{"parent": "Sales Order Status", "fieldname": fieldname},
			"fieldtype",
			"Float",
			update_modified=False,
		)
