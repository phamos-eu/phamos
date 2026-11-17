from frappe import _


def get_data():
	# The lines of Sales Orders and Sales Invoices name their ticket (phamos/phamos#1727). Frappe resolves the
	# filter on the items table's "attendee" field, as ERPNext's Item dashboard does for item_code.
	return {
		"fieldname": "attendee",
		"transactions": [{"label": _("Billing"), "items": ["Sales Order", "Sales Invoice"]}],
	}
