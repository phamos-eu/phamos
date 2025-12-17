"""Add custom location field to Event doctype for storing Jitsi/meeting links."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Create custom_location field on Event doctype."""
	custom_fields = {
		"Event": [
			{
				"fieldname": "custom_location",
				"label": "Location",
				"fieldtype": "Data",
				"insert_after": "description",
				"description": "Meeting location or URL (e.g., Jitsi link for hybrid meetings)",
			},
		]
	}
	
	create_custom_fields(custom_fields, update=True)
	frappe.db.commit()
