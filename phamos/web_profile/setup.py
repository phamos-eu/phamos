"""Custom fields and permissions the Web Profile website needs on standard doctypes (run after every
migrate)."""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, update_permission_property

# Web Page: one page per language, linked as translations (phamos/phamos#1502). The German page is
# the master; the English page points to it with "Translation Of".
WEB_PAGE_FIELDS = {
	"Web Page": [
		{
			"fieldname": "language",
			"fieldtype": "Select",
			"label": "Language",
			"options": "\nde\nen",
			"insert_after": "route",
			"description": "Page language. Use routes de/… and en/… so navbar, footer and language picker can switch.",
			"module": "Phamos",
		},
		{
			"fieldname": "translation_of",
			"fieldtype": "Link",
			"label": "Translation Of",
			"options": "Web Page",
			"insert_after": "language",
			"depends_on": "eval:doc.language && doc.language != 'de'",
			"description": "For the English page: the German page it translates.",
			"module": "Phamos",
		},
	]
}


def after_migrate():
	create_custom_fields(WEB_PAGE_FIELDS, update=True)
	ensure_employee_select_permission()


def ensure_employee_select_permission():
	"""Website Managers link the Employee of a Person Web Profile. Select lets them search Employees
	in the link field without opening Employee records. Publishing the profile of an Employee they
	cannot read needs the Employee's consent (PersonWebProfile.validate_consents)."""
	if frappe.db.exists("Custom DocPerm", {"parent": "Employee", "role": "Website Manager", "permlevel": 0}):
		return  # set already, or changed by hand in the Role Permission Manager: leave it
	add_permission("Employee", "Website Manager", ptype="select")
	update_permission_property("Employee", "Website Manager", 0, "read", 0)
