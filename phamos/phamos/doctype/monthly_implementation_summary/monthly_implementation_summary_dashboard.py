# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	# delivery_note and sales_invoice on this doc point to linked transactions.
	# fieldname + non_standard_fieldnames: safe fallback when no DN is set (query yields 0 rows).
	return {
		"fieldname": "name",
		"non_standard_fieldnames": {"Delivery Note": "name", "Sales Invoice": "name"},
		"internal_links": {"Delivery Note": "delivery_note", "Sales Invoice": "sales_invoice"},
		"transactions": [{"label": _("Related"), "items": ["Delivery Note", "Sales Invoice"]}],
	}
