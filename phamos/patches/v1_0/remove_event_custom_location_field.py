"""Remove legacy custom_location field from Event doctype."""

import frappe



def execute():
    field_name = "Event-custom_location"

    if frappe.db.exists("Custom Field", field_name):
        frappe.delete_doc("Custom Field", field_name, force=1)

    if frappe.db.has_column("Event", "custom_location"):
        frappe.db.sql("ALTER TABLE `tabEvent` DROP COLUMN `custom_location`")

    frappe.clear_cache(doctype="Event")
    frappe.db.commit()
