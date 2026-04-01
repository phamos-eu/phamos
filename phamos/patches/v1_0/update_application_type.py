import frappe

def execute():
    frappe.db.sql("""
        UPDATE `tabJob Applicant`
        SET custom_application_status = 'Received'
        WHERE custom_application_status IS NULL
        OR custom_application_status = ''
    """)