import frappe

def execute():
    frappe.db.sql("""
        UPDATE `tabImplementation`
        SET status = 'Open'
    """)
