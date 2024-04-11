import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    frappe.reload_doc("Setup", "doctype", "employee")
    create_custom_field("employee",
	    dict(fieldname="phamos_section_break", label="phamos",
		fieldtype="Section Break", insert_after="basic_details_tab"))

    create_custom_field("employee",
		dict(fieldname="activity_type", label="Activity Type",
		fieldtype="Link", options="Activity Type",
		insert_after="phamos_section_break", description='The "Activity Type" allows for categorizing tasks into specific types, such as planning, execution, communication, and proposal writing, streamlining task management and organization within the system.'))
    