import frappe
import random
from frappe.utils import getdate, get_url, format_datetime, strip_html, nowdate, getdate
from frappe import _


@frappe.whitelist()
def get_timesheets(from_date=None, to_date=None, project=None, offset=0, limit=20, sort_by=None, sort_order=None):
    user = frappe.session.user

    validate_guest_user()
    customer = get_customer_for_user(user)
    if not customer:
        frappe.throw("No Customer linked to user.", frappe.PermissionError)

    # Build dynamic filters
    conditions = " AND customer = %s"
    values = [customer]

    if from_date and to_date:
        conditions += " AND start_date <= %s AND end_date >= %s"
        values.extend([getdate(to_date), getdate(from_date)])

    elif from_date:
        conditions += " AND end_date >= %s"
        values.append(getdate(from_date))

    elif to_date:
        conditions += " AND start_date <= %s"
        values.append(getdate(to_date))

    if project:
        conditions += " AND parent_project = %s"
        values.append(project)

    valid_sort_fields = {
        "timesheet": "ts.name",
        "start_date": "ts.start_date",
        "employee_name": "ts.employee_name",
        "billing_status": "ts.custom_billing_status",
        "total_hours": "ts.total_hours",
        "billable_hours": "ts.total_billable_hours",
        "related_issue": "related_issue",
        "activity_type": "activity_type",
        "comment": "ts.customer_comment",
        "creation": "ts.creation"
    }

    order_field = valid_sort_fields.get(sort_by, "ts.creation")
    order_direction = "ASC" if sort_order == "asc" else "DESC"

    # Total count
    total = frappe.db.sql(f"""
        SELECT COUNT(*)
        FROM `tabTimesheet`
        WHERE docstatus IN (0, 1) {conditions}
    """, values)[0][0]

    timesheets = frappe.db.sql(f"""
        SELECT
            ts.name,
            ts.employee,
            ts.employee_name,
            ts.custom_billing_status,
            ts.total_hours,
            ts.total_billable_hours,
            ts.project_name,
            ts.start_date,
            ts.end_date,
            ts.creation,
            ts.customer_comment,
            ts.custom_rating,
            (
                SELECT description
                FROM `tabTimesheet Detail` td
                WHERE td.parent = ts.name
                ORDER BY td.idx
                LIMIT 1
            ) AS related_issue,
            (
                SELECT activity_type
                FROM `tabTimesheet Detail` td
                WHERE td.parent = ts.name
                ORDER BY td.idx
                LIMIT 1
            ) AS activity_type
        FROM `tabTimesheet` ts
        WHERE ts.docstatus IN (0, 1) {conditions}
        ORDER BY {order_field} {order_direction}
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
def update_customer_comment(ts_name, comment=None, custom_rating=None):
    ts = frappe.get_doc("Timesheet", ts_name)

    # Update fields in Timesheet
    if comment is not None:
        ts.db_set("customer_comment", comment)
    if custom_rating is not None:
        ts.db_set("custom_rating", custom_rating)

    ts.db_set("custom_customer_comment_timestamp", frappe.utils.now_datetime())
    ts.db_set("custom_daily_comment_report_sent", 0)

    frappe.db.commit()

    return {
        "message": "Comment sent for Review successfully.",
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

@frappe.whitelist()
def get_customer_sales_order_status():
    """Get sales order delivery status for customer portal

    Returns all sales orders linked to implementations for the logged-in customer
    with delivery status information, summary metrics, and chart data
    """
    user = frappe.session.user

    validate_guest_user()
    customer = get_customer_for_user(user)
    if not customer:
        frappe.throw("No Customer linked to user.", frappe.PermissionError)

    frappe.log_error(f"Customer Portal - User: {user}, Customer: {customer}", "SO Status Debug")

    # Get all implementations for this customer using SQL (bypasses permission check)
    implementations = frappe.db.sql("""
        SELECT name, status, department
        FROM `tabImplementation`
        WHERE customer = %s
    """, customer, as_dict=True)

    frappe.log_error(f"Found {len(implementations)} implementations: {[i.name for i in implementations]}", "SO Status Debug")

    if not implementations:
        return {
            "sales_orders": [],
            "summary": {
                "total_so_hrs": 0,
                "delivered_hrs": 0,
                "timesheet_hrs": 0,
                "remaining_hrs": 0,
                "open_so_count": 0,
                "total_so_count": 0
            },
            "chart_data": {
                "labels": ["Delivered Hrs", "Timesheet Hrs", "Remaining Hrs"],
                "values": [0, 0, 0]
            }
        }

    implementation_names = [impl.name for impl in implementations]

    # Get all OPEN sales orders for these implementations (matching Implementation doctype logic)
    sales_orders = frappe.db.sql("""
        SELECT
            so.name,
            so.customer_name as title,
            so.status,
            so.total_qty as total_hrs,
            so.transaction_date,
            so.delivery_date,
            so.per_delivered,
            so.per_billed,
            so.grand_total,
            so.custom_implementation as implementation
        FROM `tabSales Order` so
        WHERE
            so.custom_implementation IN %(implementations)s
            AND so.docstatus = 1
            AND so.status IN ('To Deliver and Bill', 'To Deliver', 'To Bill')
        ORDER BY so.transaction_date DESC
    """, {"implementations": implementation_names}, as_dict=True)

    frappe.log_error(f"Found {len(sales_orders)} sales orders", "SO Status Debug")

    total_so_hrs = 0
    total_delivered_hrs = 0
    total_timesheet_hrs = 0
    open_so_count = 0

    # Process each sales order
    for so in sales_orders:
        # Calculate delivered hours from delivery notes (matching Implementation doctype logic)
        delivered_hrs = frappe.db.sql("""
            SELECT SUM(dni.qty) as delivered_qty
            FROM `tabDelivery Note Item` dni
            JOIN `tabDelivery Note` dn ON dn.name = dni.parent
            WHERE
                dni.against_sales_order = %s
                AND dn.docstatus = 1
                AND dn.status IN ('Completed', 'To Bill')
        """, so.name, as_dict=True)

        so.delivered_hrs = delivered_hrs[0].delivered_qty if delivered_hrs[0].delivered_qty else 0
        so.remaining_hrs = so.total_hrs - so.delivered_hrs

        # Add to totals
        total_so_hrs += so.total_hrs or 0
        total_delivered_hrs += so.delivered_hrs or 0

        # Count open sales orders (all fetched orders are open based on our query)
        open_so_count += 1

    # Calculate billable timesheet hours (not on delivery note) - matching Implementation doctype logic
    # Get projects for these implementations using SQL
    projects = frappe.db.sql("""
        SELECT name
        FROM `tabProject`
        WHERE custom_implementation IN %(implementations)s
    """, {"implementations": implementation_names}, as_dict=True)

    project_names = [p.name for p in projects]

    if project_names:
        timesheet_hrs_result = frappe.db.sql("""
            SELECT SUM(td.hours) as timesheet_hrs
            FROM `tabTimesheet` t
            JOIN `tabTimesheet Detail` td ON t.name = td.parent
            WHERE
                td.is_billable = 1
                AND t.docstatus = 0
                AND td.project IN %(projects)s
                AND td.custom_implementation IN %(implementations)s
                AND t.custom_delivery_note IS NULL
        """, {"projects": project_names, "implementations": implementation_names}, as_dict=True)

        total_timesheet_hrs = timesheet_hrs_result[0].timesheet_hrs if timesheet_hrs_result and timesheet_hrs_result[0].timesheet_hrs else 0

    # Calculate remaining hours: Total SO Hours - (Delivered Hours + Timesheet Hours)
    total_remaining_hrs = total_so_hrs - (total_delivered_hrs + total_timesheet_hrs)

    # Prepare chart data (same as Implementation doctype - percentage chart)
    chart_data = {
        "labels": ["Delivered Hrs", "Timesheet Hrs", "Remaining Hrs"],
        "values": [
            float(total_delivered_hrs),
            float(total_timesheet_hrs),
            float(total_remaining_hrs)
        ]
    }

    result = {
        "sales_orders": sales_orders,
        "summary": {
            "total_so_hrs": total_so_hrs,
            "delivered_hrs": total_delivered_hrs,
            "timesheet_hrs": total_timesheet_hrs,
            "remaining_hrs": total_remaining_hrs,
            "open_so_count": open_so_count,
            "total_so_count": len(sales_orders)
        },
        "chart_data": chart_data
    }

    frappe.log_error(f"Returning result with {len(sales_orders)} orders", "SO Status Debug")
    return result


def send_daily_timesheet_comment_summary():
    rows = frappe.db.sql(
        """
        SELECT
            ts.name AS timesheet,
            ts.customer_comment AS comment,
            ts.custom_customer_comment_timestamp AS comment_timestamp,
            ts.custom_rating AS rating,
            ts.employee AS employee,
            ts.customer AS customer,
            ts.parent_project AS parent_project,
            pr.project_owner AS project_owner
        FROM `tabTimesheet` ts
        LEFT JOIN `tabProject` pr ON pr.name = ts.parent_project
        WHERE
            ts.docstatus IN (0, 1)
            AND ts.customer_comment IS NOT NULL
            AND ts.customer_comment != ''
            AND (ts.custom_daily_comment_report_sent IS NULL
                 OR ts.custom_daily_comment_report_sent = 0)
            AND pr.project_owner IS NOT NULL
        """,
        as_dict=True,
    )

    if not rows:
        return

    owner_map = {}
    for row in rows:
        owner = row.project_owner
        if not owner:
            continue
        owner_map.setdefault(owner, []).append(row)

    for owner, items in owner_map.items():
        if not items:
            continue

        customers = sorted({r.customer for r in items})
        if not customers:
            subject = _("Daily Summary: New Timesheet Comments")
        elif len(customers) == 1:
            subject = _("Daily Summary: New Timesheet Comments for Customer {0}").format(customers[0])
        else:
            subject = _("Daily Summary: New Timesheet Comments for Customers {0}").format(", ".join(customers))

        html_rows = []
        for r in items:
            ts_link = get_url(f"/app/timesheet/{r.timesheet}")
            preview = truncate(strip_html(r.comment))

            full_name = frappe.db.get_value("Customer", r.customer, "customer_name")
            commented_by_label = full_name or r.customer

            comment_dt = r.comment_timestamp
            if comment_dt:
                comment_date_str = format_datetime(comment_dt, "yyyy-MM-dd HH:mm")
            else:
                comment_date_str = ""

            rating_value = int(r.rating or 0)
            stars = "★" * rating_value + "☆" * (5 - rating_value)

            html_rows.append(
                f"""
                <tr>
                    <td><a href="{ts_link}">{frappe.utils.escape_html(r.timesheet)}</a></td>
                    <td>{frappe.utils.escape_html(preview)}</td>
                    <td>{stars}</td>
                    <td>{frappe.utils.escape_html(commented_by_label)}</td>
                    <td>{frappe.utils.escape_html(comment_date_str)}</td>
                </tr>
                """
            )

        if not html_rows:
            continue

        table_html = f"""
            <p>{_('Hello')},</p>
            <p>{_('Here is your daily summary of new timesheet comments from the customer portal:')}</p>
            <table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-size: 12px;">
                <thead style="background-color: #f5f5f5;">
                    <tr>
                        <th style="text-align:left;">{_('Timesheet')}</th>
                        <th style="text-align:left;">{_('Comment Preview')}</th>
                        <th style="text-align:left;">{_('Rating')}</th>
                        <th style="text-align:left;">{_('Commented By')}</th>
                        <th style="text-align:left;">{_('Comment Date')}</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(html_rows)}
                </tbody>
            </table>
            <p style="margin-top: 12px;">
                {_('This email contains only new comments that have not been reported in a previous daily summary.')}</p>
            <p>{_('Best regards')}<br>{_('ERPNext System')}</p>
        """

        recipients = [owner]
        try:
            frappe.sendmail(
                recipients=recipients,
                subject=subject,
                message=table_html,
                now=True,
            )

            ts_names = [r.timesheet for r in items]
            if ts_names:
                frappe.db.sql(
                    """
                    UPDATE `tabTimesheet`
                    SET custom_daily_comment_report_sent = 1
                    WHERE name IN ({placeholders})
                    """.format(
                        placeholders=", ".join(["%s"] * len(ts_names))
                    ),
                    ts_names,
                )
                frappe.db.commit()

        except Exception:
            frappe.log_error(
                title="Daily Timesheet Comment Summary: Email Send Failed",
                message=frappe.get_traceback(),
            )


def truncate(text, length=100):
    text = (text or "").strip()
    return text if len(text) <= length else text[:length].rstrip() + "…"


def send_monthly_comment_summary():
    # Fetch current month's customer comments
    timesheets = frappe.db.sql("""
        SELECT
            ts.name AS timesheet,
            ts.customer AS customer,
            ts.customer_comment AS comment,
            ts.custom_rating AS rating,
            ts.modified AS comment_timestamp
        FROM `tabTimesheet` ts
        WHERE ts.customer_comment IS NOT NULL
          AND ts.customer_comment != ''
          AND MONTH(ts.modified) = MONTH(CURDATE())
          AND YEAR(ts.modified) = YEAR(CURDATE())
        ORDER BY ts.customer, ts.modified
    """, as_dict=True)

    if not timesheets:
        return

    # Group by customer
    customers_map = {}
    for r in timesheets:
        customers_map.setdefault(r.customer, []).append(r)

    for customer, items in customers_map.items():

        if not items:
            continue

        # Customer email
        email = frappe.db.get_value("Customer", customer, "email_id")

        # If customer email not found, fetch from primary Contact
        if not email:
            email = frappe.db.sql("""
                SELECT ce.email_id
                FROM `tabContact` c
                JOIN `tabDynamic Link` dl ON dl.parent = c.name
                JOIN `tabContact Email` ce ON ce.parent = c.name
                WHERE dl.link_doctype = 'Customer'
                AND dl.link_name = %s
                ORDER BY c.is_primary_contact DESC
                LIMIT 1
            """, (customer,), as_dict=True)

            email = email[0].email_id if email else None

        if not email:
            frappe.logger().info(f"No email found for customer {customer}, skipping...")
            continue


        subject = _("Monthly Summary: Timesheet Comments for {0}").format(customer)

        html_rows = []
        for r in items:
            ts_link = get_url(f"/app/timesheet/{r.timesheet}")
            preview = (strip_html(r.comment) or "")[:200]

            cust_name = frappe.db.get_value("Customer", r.customer, "customer_name") or r.customer
            comment_date_str = format_datetime(r.comment_timestamp, "yyyy-MM-dd HH:mm") if r.comment_timestamp else ""

            rating_value = int(r.rating or 0)
            stars = "★" * rating_value + "☆" * (5 - rating_value)

            html_rows.append(f"""
                <tr>
                    <td><a href="{ts_link}">{frappe.utils.escape_html(r.timesheet)}</a></td>
                    <td>{frappe.utils.escape_html(preview)}</td>
                    <td>{stars}</td>
                    <td>{frappe.utils.escape_html(cust_name)}</td>
                    <td>{frappe.utils.escape_html(comment_date_str)}</td>
                </tr>
            """)

        if not html_rows:
            continue

        table_html = f"""
            <p>Dear {frappe.utils.escape_html(cust_name)},</p>
            <p>This is a monthly summary of the latest comments on your timesheets.</p>
            <p>
                Feel free to use the comment function in your Customer Portal to ask questions
                or share feedback. Your input helps us improve transparency and align our work
                even more closely with your needs. We look forward to your contributions!
            </p>

            <table border="1" cellpadding="6" cellspacing="0"
                   style="border-collapse: collapse; font-size: 12px;">
                <thead style="background-color: #f5f5f5;">
                    <tr>
                        <th>Timesheet</th>
                        <th>Comment Preview</th>
                        <th>Rating</th>
                        <th>Commented By</th>
                        <th>Comment Date</th>
                    </tr>
                </thead>
                <tbody>
                    {''.join(html_rows)}
                </tbody>
            </table>

            <p style="margin-top: 12px;">Your Phamos Team</p>
        """

        try:
            frappe.sendmail(
                recipients=[email],
                subject=subject,
                message=table_html,
                now=True,
            )

        except Exception:
            frappe.log_error(
                title="Monthly Timesheet Comment Summary: Email Send Failed",
                message=frappe.get_traceback()
            )



def send_daily_birthday_wishes():
    today = getdate(nowdate())
    site_url = frappe.utils.get_url()

    birthday_image_urls = [
        "/assets/phamos/images/birthday_cards/BW2.png",
        "/assets/phamos/images/birthday_cards/BW3.png",
        "/assets/phamos/images/birthday_cards/BW4.png",
        "/assets/phamos/images/birthday_cards/BW5.png",
        "/assets/phamos/images/birthday_cards/BW6.png",
        "/assets/phamos/images/birthday_cards/BW7.png",
        "/assets/phamos/images/birthday_cards/BW8.png",
        "/assets/phamos/images/birthday_cards/BW9.png",
    ]

    anniversary_image_urls = [
        "/assets/phamos/images/anniversary_cards/WA1.png",
        "/assets/phamos/images/anniversary_cards/WA2.png",
        "/assets/phamos/images/anniversary_cards/WA3.png",
        "/assets/phamos/images/anniversary_cards/WA4.png",
        "/assets/phamos/images/anniversary_cards/WA5.png",
        "/assets/phamos/images/anniversary_cards/WA6.png",
        "/assets/phamos/images/anniversary_cards/WA7.png",
        "/assets/phamos/images/anniversary_cards/WA8.png",
        "/assets/phamos/images/anniversary_cards/WA9.png",
        "/assets/phamos/images/anniversary_cards/WA10.png",
    ]

    employees = frappe.get_all(
        "Employee",
        filters={
            "status": "Active",
            "user_id": ["is", "set"]
        },
        fields=["name", "employee_name", "date_of_birth", "date_of_joining", "user_id"]
    )

    for emp in employees:

        # --- Birthday Check ---
        if emp.date_of_birth:
            dob = getdate(emp.date_of_birth)
            if dob.day == today.day and dob.month == today.month:
                random_image = random.choice(birthday_image_urls)
                full_image_url = f"{site_url}{random_image}"

                message = f"""
                    <div style="text-align:center; font-family: Arial;">
                        <h2>Happy Birthday {emp.employee_name} 🎉</h2>
                        <img src="{full_image_url}" 
                             style="width:100%; max-width:500px; border-radius:12px; margin-top:10px;">
                    </div>
                """

                frappe.sendmail(
                    recipients=[emp.user_id],
                    subject="Happy Birthday 🎉",
                    message=message
                )

        # --- Work Anniversary Check ---
        if emp.date_of_joining:
            doj = getdate(emp.date_of_joining)

            years_completed = today.year - doj.year
            if doj.day == today.day and doj.month == today.month and years_completed > 0:

                random_image = random.choice(anniversary_image_urls)
                full_image_url = f"{site_url}{random_image}"

                message = f"""
                    <div style="text-align:center; font-family: Arial;">
                        <h2>Happy Work Anniversary {emp.employee_name} 🏆</h2>
                        <p style="font-size:16px;">
                            Congratulations on completing <strong>{years_completed} year{'s' if years_completed > 1 else ''}</strong> with us!
                        </p>
                        <img src="{full_image_url}" 
                             style="width:100%; max-width:500px; border-radius:12px; margin-top:10px;">
                    </div>
                """

                frappe.sendmail(
                    recipients=[emp.user_id],
                    subject=f"Happy Work Anniversary 🏆 - {years_completed} Year{'s' if years_completed > 1 else ''}!",
                    message=message
                )