import frappe

def execute():
    if not frappe.db.has_column("Job Applicant", "custom_application_status"):
        return

    frappe.db.sql("""
        UPDATE `tabJob Applicant`
        SET custom_application_status = 'Received'
        WHERE custom_application_status IS NULL
        OR custom_application_status = ''
    """)
    frappe.db.commit()