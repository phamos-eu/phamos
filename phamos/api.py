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

    # Total count with filters
    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {conditions}
    """, values)[0][0]

    # Timesheet rows with filters
    timesheets = frappe.db.sql(f"""
        SELECT name, employee, custom_billing_status, project_owner, total_hours,
               total_billable_hours, project_name, start_date, end_date, creation, customer_comment
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {conditions}
        ORDER BY creation DESC
        LIMIT {limit} OFFSET {offset}
    """, values, as_dict=True)

    return {"timesheets": timesheets, "total": total}

@frappe.whitelist()
def get_projects_for_logged_in_customer():
    user = frappe.session.user

    #validate user
    validate_guest_user()

    customer = get_customer_for_user(user)  # uses helper function below

    if not customer:
        return []

    return frappe.get_list(
        "Project",
        filters={"customer": customer},
        fields=["name", "project_name"]
    )

def get_customer_for_user(user):
    # Get all Contact names linked to this User
    contacts = frappe.get_list(
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


@frappe.whitelist()
def get_timesheet_totals(from_date=None, to_date=None, project=None):
    user = frappe.session.user
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
        conditions += " AND parent_project = %s"
        values.append(project)

    # apply filters here
    data = frappe.db.sql(f"""
        SELECT total_hours, total_billable_hours
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {conditions}
    """, values, as_dict=True)

    total_hours = sum([float(d.total_hours or 0) for d in data])
    billable_hours = sum([float(d.total_billable_hours or 0) for d in data])

    return {
        "total_hours": total_hours,
        "billable_hours": billable_hours
    }


@frappe.whitelist()
def get_graph_data(from_date=None, to_date=None, project=None):
    filters = ""
    if from_date:
        filters += f" AND start_date >= '{from_date}'"
    if to_date:
        filters += f" AND end_date <= '{to_date}'"
    if project:
        filters += f" AND project = '{project}'"

    data = frappe.db.sql(f"""
        SELECT name, start_date, total_hours, total_billable_hours, project_name
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {filters}
        ORDER BY start_date
    """, as_dict=True)

    return {"timesheets": data}




