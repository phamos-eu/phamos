from frappe import _


def get_delivery_note_dashboard_data(data):
	data["non_standard_fieldnames"] = {
		**data.get("non_standard_fieldnames", {}),
		"Timesheet": "custom_delivery_note",
	}
	data["transactions"].append(
		{"label": _("Implementation Specific"), "items": ["Timesheet"]}
	)
	return data
