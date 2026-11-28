from frappe import _


def get_lead_dashboard_data(data):
	"""Show the Lead's event tickets under its connections, for marketing (phamos/phamos#2215).

	Event Ticket Order and Attendee link back with the fieldname "lead", which ERPNext's Lead
	dashboard already uses, so no non_standard_fieldnames are needed.
	"""
	data["transactions"].append({"label": _("Events"), "items": ["Event Ticket Order", "Attendee"]})
	return data
