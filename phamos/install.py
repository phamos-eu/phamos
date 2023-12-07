import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_migrate():
	create_custom_fields(get_custom_fields())


def before_uninstall():
	delete_custom_fields(get_custom_fields())


def delete_custom_fields(custom_fields):
	for doctype, fields in custom_fields.items():
		for field in fields:
			custom_field_name = frappe.db.get_value(
				"Custom Field", dict(dt=doctype, fieldname=field.get("fieldname"))
			)
			if custom_field_name:
				frappe.delete_doc("Custom Field", custom_field_name)

		frappe.clear_cache(doctype=doctype)


def get_custom_fields():
	custom_fields_about_us = [
		{
			"label": "Phamos",
			"fieldname": "phamos_section",
			"fieldtype": "Section Break",
		},
		{
			"label": "Team Profile Links",
			"fieldname": "team_profile_links",
			"fieldtype": "Table",
			"options": "Phamos Team",
			"insert_after": "phamos_section"
		}
	]



	return {
		"About Us Settings": custom_fields_about_us
	}
