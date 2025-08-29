import frappe
from frappe import _

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.throw(_("Please login to access your timesheets"), frappe.PermissionError)

    context.title = "My Timesheets"
    context.breadcrumbs = [
        {"label": "Home", "url": "/"},
        {"label": "My Timesheets", "url": "/timesheets"}
    ]


