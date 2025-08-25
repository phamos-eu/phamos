import frappe
from frappe.utils import nowdate

def execute():
    dummy_date = nowdate()

    if frappe.db.exists("DocType", "Implementation"):
        try:
            frappe.db.sql("""
                UPDATE `tabImplementation`
                SET from_date = %s
                WHERE from_date IS NOT NULL AND from_date NOT LIKE '____-__-__'
            """, dummy_date)

            frappe.db.sql("""
                UPDATE `tabImplementation`
                SET to_date = %s
                WHERE to_date IS NOT NULL AND to_date NOT LIKE '____-__-__'
            """, dummy_date)

            frappe.db.commit()
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "Implementation Patch Error")
