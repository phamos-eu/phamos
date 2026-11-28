from frappe import _


def get_data():
	return {
		"fieldname": "event",
		"non_standard_fieldnames": {"Newsletter": "custom_marketing_content", "Checklist": "reference_record"},
		"transactions": [
			# The orders of the event and their tickets (phamos/phamos#1728).
			{"label": _("Tickets"), "items": ["Event Ticket Order", "Attendee"]},
			{"label": _("Marketing"), "items": ["Newsletter", "Checklist"]},
		],
	}
