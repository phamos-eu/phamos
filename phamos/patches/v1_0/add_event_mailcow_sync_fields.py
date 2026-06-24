"""Add Mailcow sync custom fields to Event doctype."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
	"""Create Mailcow sync fields on Event doctype."""
	custom_fields = {
		"Event": [
			{
				"fieldname": "custom_mailcow_uid",
				"label": "Mailcow UID",
				"fieldtype": "Data",
				"insert_after": "custom_location",
				"hidden": 1,
				"read_only": 1,
			},
			{
				"fieldname": "custom_mailcow_seq",
				"label": "Mailcow Sequence",
				"fieldtype": "Int",
				"insert_after": "custom_mailcow_uid",
				"default": "0",
				"hidden": 1,
				"read_only": 1,
			},
			{
				"fieldname": "custom_mailcow_synched",
				"label": "Mailcow Synced",
				"fieldtype": "Check",
				"insert_after": "custom_mailcow_seq",
				"default": "0",
				"hidden": 1,
				"read_only": 1,
			},
			{
				"fieldname": "custom_mailcow_etag",
				"label": "Mailcow ETag",
				"fieldtype": "Data",
				"insert_after": "custom_mailcow_synched",
				"hidden": 1,
				"read_only": 1,
			},
		]
	}

	create_custom_fields(custom_fields, update=True)
	frappe.db.commit()
