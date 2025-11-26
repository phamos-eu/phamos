import frappe
from frappe.utils import getdate, get_url, format_datetime, strip_html
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

    if from_date:
        conditions += " AND start_date >= %s"
        values.append(getdate(from_date))

    if to_date:
        conditions += " AND end_date <= %s"
        values.append(getdate(to_date))

    if project:
        conditions += " AND parent_project = %s"
        values.append(project)

    valid_sort_fields = {
        "timesheet": "ts.name",
        "start_date": "ts.start_date",
        "billing_status": "ts.custom_billing_status",
        "total_hours": "ts.total_hours",
        "billable_hours": "ts.total_billable_hours",
        "related_issue": "related_issue",
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
            ts.custom_billing_status,
            ts.project_owner,
            ts.total_hours,
            ts.total_billable_hours,
            ts.project_name,
            ts.start_date,
            ts.end_date,
            ts.creation,
            ts.customer_comment,
            (
                SELECT description
                FROM `tabTimesheet Detail` td
                WHERE td.parent = ts.name
                ORDER BY td.idx
                LIMIT 1
            ) AS related_issue
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
