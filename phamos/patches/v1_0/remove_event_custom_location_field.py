"""Remove legacy custom_location field from Event doctype."""

import frappe
from frappe.model import delete_fields



def execute():
    field_name = "Event-custom_location"

    if frappe.db.exists("Custom Field", field_name):
        frappe.delete_doc("Custom Field", field_name, force=1)

    # Use framework API to remove field metadata and column safely.
    delete_fields({"Event": ["custom_location"]}, delete=1)

    frappe.clear_cache(doctype="Event")
    frappe.db.commit()
