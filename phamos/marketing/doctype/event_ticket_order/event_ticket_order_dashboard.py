from frappe import _


def get_data():
	# Attendees, Sales Orders and Sales Invoices (credit notes included) point to the order through the same
	# field (phamos/phamos#1727, phamos/phamos#1729).
	return {
		"fieldname": "event_ticket_order",
		"transactions": [
			{"label": _("Tickets"), "items": ["Attendee"]},
			{"label": _("Billing"), "items": ["Sales Order", "Sales Invoice"]},
		],
	}
