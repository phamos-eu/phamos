# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Description column in the item tables of sales and purchase documents (#1858).

Called from after_migrate. Idempotent. Ported from the aquarath app (aquarath/aquarath@d9acb0b7).

The item description is shown as a grid column. The row grows with its text, so the description
can be read and edited in place (public/css/item_grid_description.bundle.css). The widths below
make room for it.

The app owns this layout: every migrate resets these property setters, so changes made through
Customize Form don't survive.
"""

import frappe

MODULE = "Phamos"

# Grid columns per child doctype: fieldname -> width (out of 10).
ITEM_GRID_COLUMNS = {
	"Quotation Item": {"item_code": 2, "description": 3, "qty": 1, "rate": 2, "amount": 2},
	"Sales Order Item": {
		"item_code": 2,
		"description": 3,
		"delivery_date": 1,
		"qty": 1,
		"rate": 1,
		"amount": 2,
	},
	"Purchase Order Item": {
		"item_code": 2,
		"description": 3,
		"schedule_date": 1,
		"qty": 1,
		"uom": 1,
		"rate": 1,
		"amount": 1,
	},
	# custom_ref_doc is phamos' own column (fixtures/custom_field.json); rate leaves the grid
	# to make room for it, see ITEM_GRID_HIDDEN.
	"Delivery Note Item": {
		"custom_ref_doc": 1,
		"item_code": 2,
		"description": 3,
		"qty": 1,
		"uom": 1,
		"amount": 2,
	},
	"Sales Invoice Item": {"item_code": 2, "description": 3, "qty": 1, "rate": 2, "amount": 2},
}

# Standard grid columns taken out of the grid so the widths above fit into 10.
ITEM_GRID_HIDDEN = {
	"Delivery Note Item": ("rate",),
}


def get_property_setters():
	"""[(doctype, fieldname, property, value, property_type)] for the item grids."""
	setters = []
	for doctype, columns in ITEM_GRID_COLUMNS.items():
		setters.append((doctype, "description", "in_list_view", "1", "Check"))
		hidden = ITEM_GRID_HIDDEN.get(doctype, ())
		setters += [(doctype, fieldname, "in_list_view", "0", "Check") for fieldname in hidden]
		setters += [
			(doctype, fieldname, "columns", str(width), "Int") for fieldname, width in columns.items()
		]
	return setters


def after_migrate():
	"""Create or update the item grid property setters, tagged with this app's module."""
	for doctype, fieldname, prop, value, property_type in get_property_setters():
		filters = {"doc_type": doctype, "field_name": fieldname, "property": prop, "doctype_or_field": "DocField"}
		name = frappe.db.get_value("Property Setter", filters)
		if name:
			frappe.db.set_value("Property Setter", name, {"value": value, "module": MODULE})
			continue
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				**filters,
				"value": value,
				"property_type": property_type,
				"module": MODULE,
				"is_system_generated": 1,
			}
		).insert(ignore_permissions=True)
	for doctype in ITEM_GRID_COLUMNS:
		frappe.clear_cache(doctype=doctype)
