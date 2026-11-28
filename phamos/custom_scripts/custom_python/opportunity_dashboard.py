from frappe import _


def get_opportunity_dashboard_data(data):
	"""Show the Implementation Features configured in this Opportunity (#1968) under its connections.

	Implementation Feature links back with the fieldname "opportunity", which ERPNext's Opportunity
	dashboard already uses for its own links, so no non_standard_fieldnames are needed.
	"""
	data["transactions"].append({"label": _("Implementation"), "items": ["Implementation Feature"]})
	return data
