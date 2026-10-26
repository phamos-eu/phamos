from frappe import _


def get_data():
	return {
		"fieldname": "ticket_order",
		"transactions": [{"label": _("Tickets"), "items": ["Attendee"]}],
	}
