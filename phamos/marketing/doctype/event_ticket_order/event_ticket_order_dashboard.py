from frappe import _


def get_data():
	# Sales Orders and Sales Invoices (credit notes included) point to the order (phamos/phamos#1727).
	return {
		"fieldname": "ticket_order",
		"non_standard_fieldnames": {"Sales Order": "event_ticket_order", "Sales Invoice": "event_ticket_order"},
		"transactions": [
			{"label": _("Tickets"), "items": ["Attendee"]},
			{"label": _("Billing"), "items": ["Sales Order", "Sales Invoice"]},
		],
	}
