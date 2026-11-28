# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe import _


def get_data():
	# Delivery Notes and Sales Invoices point at their MIS; the MIS keeps no link to them (#1987).
	return {
		"fieldname": "custom_monthly_implementation_summary",
		"internal_links": {
			"Sales Order": ["sales_order_status_information", "sales_order"],
		},
		"transactions": [
			{"label": _("Related"), "items": ["Sales Order", "Delivery Note", "Sales Invoice"]},
		],
	}
