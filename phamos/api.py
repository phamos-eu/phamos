import frappe
from frappe.apps import _
from frappe.utils import getdate
from frappe import _

@frappe.whitelist()
def get_timesheets(from_date=None, to_date=None, project=None, offset=0, limit=20):
    user = frappe.session.user

    #validate user
    validate_guest_user()
    
    customer = get_customer_for_user(user)
    
    if not customer:
        frappe.throw("No Customer linked to user.", frappe.PermissionError)
        
    filters = {"docstatus": 1, "customer": customer}

    if from_date:
        filters["start_date"] = [">=", getdate(from_date)]
    if to_date:
        filters["end_date"] = ["<=", getdate(to_date)]
    if project:
        filters["parent_project"] = project

    total = frappe.db.count("Timesheet", filters)

    timesheets = frappe.get_all("Timesheet",
        filters=filters,
        fields=[
            "name", "employee", "employee_name", "custom_billing_status", "project_owner",
            "timesheet_status", "total_hours", "total_billable_hours",
            "start_date", "end_date", "creation"
        ],
        order_by="creation desc",
        start=int(offset),
        page_length=int(limit),
        ignore_permissions=True
    )

    return {"timesheets": timesheets, "total": total}

@frappe.whitelist()
def get_projects_for_logged_in_customer():
    user = frappe.session.user

    #validate user
    validate_guest_user()

    customer = get_customer_for_user(user)  # uses helper function below

    if not customer:
        return []

    return frappe.get_all(
        "Project",
        filters={"customer": customer},
        fields=["name", "project_name"]
    )

def get_customer_for_user(user):
    # Get all Contact names linked to this User
    contacts = frappe.get_all(
        "Contact", filters={"user": user}, fields=["name"]
    )

    if not contacts:
        return None

    # Look for any linked Customer via Dynamic Link
    for contact in contacts:
        link = frappe.db.get_value(
            "Dynamic Link",
            {
                "parenttype": "Contact",
                "parent": contact.name,
                "link_doctype": "Customer"
            },
            "link_name"
        )
        if link:
            return link  # Return the first found customer

    return None

def validate_guest_user():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)