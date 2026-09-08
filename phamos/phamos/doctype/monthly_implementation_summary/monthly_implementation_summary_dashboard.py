# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	return {
		"fieldname": "name",
		"internal_links": {
			"Sales Order": ["mis_delivery_notes", "sales_order"],
			"Delivery Note": ["mis_delivery_notes", "delivery_note"],
			"Sales Invoice": ["mis_sales_invoices", "sales_invoice"],
		},
		"transactions": [
			{"label": _("Related"), "items": ["Sales Order", "Delivery Note", "Sales Invoice"]},
		],
	}

