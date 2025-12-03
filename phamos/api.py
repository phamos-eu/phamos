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
    # Build dynamic filters
    conditions = " AND customer = %s"
    values = [customer]

    if from_date:
        conditions += " AND start_date >= %s"
        values.append(getdate(from_date))

    if to_date:
        conditions += " AND end_date <= %s"
        values.append(getdate(to_date))

    if project:
        conditions += " AND parent_project = %s"
        values.append(project)

    # Total count with filters
    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {conditions}
    """, values)[0][0]

    # Timesheet rows with filters
    timesheets = frappe.db.sql(f"""
        SELECT name, employee, custom_billing_status, project_owner, total_hours,
               total_billable_hours, project_name, start_date, end_date, creation, customer_comment, custom_approval
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

@frappe.whitelist()
def update_customer_comment(ts_name, comment=None, custom_discount_request=None, custom_rating=None):
    ts = frappe.get_doc("Timesheet", ts_name)

    # Update fields in Timesheet
    if comment is not None:
        ts.db_set("customer_comment", comment)
    if custom_discount_request is not None:
        ts.db_set("custom_discount_request", custom_discount_request)
    if custom_rating is not None:
        ts.db_set("custom_rating", custom_rating)

    # Always treat it as Pending unless PM later updates approval
    approval_status = ts.get("custom_approval") or "Pending"

    # Send email notification to Project Owner/Deputy
    if ts.parent_project:
        project = frappe.get_doc("Project", ts.parent_project)
        recipients = [r for r in [project.get("project_owner"), project.get("project_deputy")] if r]
        if recipients:
            frappe.sendmail(
                recipients=recipients,
                subject=f"New Discount/Comment Request for Timesheet: {ts.name}",
                message=f"""
                    <p>Hello,</p>
                    <p>A new request has been submitted by a customer on Timesheet <b>{ts.name}</b>.</p>
                    <p><b>Comment:</b> {comment or '-'}<br>
                    <b>Discount Request:</b> {custom_discount_request or '-'}<br>
                    <b>Rating:</b> {custom_rating or '-'}</p>
                    <p>Please review this Timesheet and set <b>Approval</b> to either <b>Accept</b> or <b>Reject</b>.</p>
                    <p>Status: <b>Pending</b></p>
                    <p>Regards,<br>ERPNext System</p>
                """,
                now=True
            )

    frappe.db.commit()

    return {
        "message": "Comment sent for approval successfully.",
        "approval": approval_status
    }



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

    # build conditions dynamically
    conditions = " AND customer = %s"
    values = [customer]

    if from_date:
        conditions += " AND start_date >= %s"
        values.append(getdate(from_date))

    if to_date:
        conditions += " AND end_date <= %s"
        values.append(getdate(to_date))

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
    user = frappe.session.user
    validate_guest_user()
    
    customer = get_customer_for_user(user)
    if not customer:
        frappe.throw("No Customer linked to user.", frappe.PermissionError)

    filters = f" AND customer = '{customer}'"
    if from_date:
        filters += f" AND start_date >= '{from_date}'"
    if to_date:
        filters += f" AND end_date <= '{to_date}'"
    if project:
        filters += f" AND parent_project = '{project}'"

    data = frappe.db.sql(f"""
        SELECT 
            name,
            start_date,
            total_hours,
            total_billable_hours,
            parent_project,
            COALESCE(NULLIF(project_name, ''), parent_project) as project_label,
            employee
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {filters}
        ORDER BY start_date
    """, as_dict=True)

    return {"timesheets": data}


# Sales Order KPI Display Preferences API
@frappe.whitelist()
def get_sales_order_kpi_preference():
    """Get user's preferred KPI display mode for Sales Orders"""
    user = frappe.session.user
    
    # Check if preference exists in user defaults
    preference = frappe.db.get_value(
        "DefaultValue",
        {"parent": user, "defkey": "sales_order_kpi_display_mode"},
        "defvalue"
    )
    
    return preference or "all"


@frappe.whitelist()
def set_sales_order_kpi_preference(mode):
    """Set user's preferred KPI display mode for Sales Orders
    
    Args:
        mode: One of 'all', 'indicators', 'progress_bars', 'cards', 'html_section'
    """
    valid_modes = ['all', 'indicators', 'progress_bars', 'cards', 'html_section']
    
    if mode not in valid_modes:
        frappe.throw(_("Invalid display mode. Choose from: {0}").format(", ".join(valid_modes)))
    
    user = frappe.session.user
    
    # Set user default
    frappe.db.set_default("sales_order_kpi_display_mode", mode, user)
    frappe.db.commit()
    
    return {"success": True, "mode": mode, "message": _("Display preference saved successfully")}


@frappe.whitelist()
def get_sales_order_kpi_stats(sales_order):
    """Get detailed KPI statistics for a Sales Order
    
    Returns delivery and billing details including related documents
    """
    if not frappe.has_permission("Sales Order", "read", sales_order):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    
    so = frappe.get_doc("Sales Order", sales_order)
    
    # Get related documents
    delivery_notes = frappe.get_all(
        "Delivery Note Item",
        filters={"against_sales_order": sales_order, "docstatus": 1},
        fields=["parent", "qty", "item_code"],
        group_by="parent"
    )
    
    sales_invoices = frappe.get_all(
        "Sales Invoice Item",
        filters={"sales_order": sales_order, "docstatus": 1},
        fields=["parent", "qty", "amount", "item_code"],
        group_by="parent"
    )
    
    # Calculate totals
    total_qty = sum([item.qty for item in so.items])
    delivered_qty = sum([item.delivered_qty for item in so.items])
    billed_qty = sum([item.billed_qty if hasattr(item, 'billed_qty') else 0 for item in so.items])
    
    return {
        "per_delivered": so.per_delivered,
        "per_billed": so.per_billed,
        "total_qty": total_qty,
        "delivered_qty": delivered_qty,
        "pending_qty": total_qty - delivered_qty,
        "billed_qty": billed_qty,
        "total_amount": so.grand_total,
        "billed_amount": so.grand_total * (so.per_billed / 100),
        "pending_amount": so.grand_total * ((100 - so.per_billed) / 100),
        "delivery_notes": [dn.parent for dn in delivery_notes],
        "sales_invoices": [si.parent for si in sales_invoices],
        "status": so.status,
        "delivery_status": so.delivery_status,
        "billing_status": so.billing_status
    }





