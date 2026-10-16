from frappe import _


def get_data():
	return {
		"fieldname": "event",
		"non_standard_fieldnames": {"Newsletter": "custom_marketing_content", "Checklist": "reference_record"},
		"transactions": [
			{"label": _("Attendees"), "items": ["Attendee"]},
			{"label": _("Marketing"), "items": ["Newsletter", "Checklist"]},
		],
	}
