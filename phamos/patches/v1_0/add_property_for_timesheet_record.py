
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

def execute():
	frappe.reload_doc("phamos", "doctype", "timesheet_record")
	make_property_setter("Timesheet Record", "activity_type", "allow_on_submit", 0, "Check")
	make_property_setter("Timesheet Record", "activity_type", "reqd", 0, "Check")
