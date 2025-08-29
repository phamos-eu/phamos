# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

# import frappe


def execute(filters=None):
	columns, data = [], []
	return columns, data
# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate

def execute(filters=None):
    if not filters:
        filters = {}

    year = int(filters.get("year") or frappe.utils.nowdate().split("-")[0])

    data = []
    quarter_totals = [0] * 8  # For 8 numeric columns (excluding Month)

    def add_quarter_row(qtr_label):
        return [f"**{qtr_label} Total**"] + [round(val, 2) for val in quarter_totals]

    for month in range(1, 13):
        month_name = frappe.utils.formatdate(f"{year}-{month:02d}-01", "MMMM")
        month_start = f"{year}-{month:02d}-01"
        month_end = frappe.utils.get_last_day(month_start)

        # Total Hours (all projects)
        total_hours = frappe.db.sql("""
            SELECT SUM(actual_time)/3600
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND docstatus = '1'
        """, (month_start, month_end))[0][0] or 0

        # Total Customer Hours
        customer_hours = frappe.db.sql("""
            SELECT SUM(actual_time)/3600
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND project NOT IN (%s, %s)
            AND docstatus = '1'
        """, (month_start, month_end, "PROJ-0055", "P-0230"))[0][0] or 0

        # Billable Customer Hours
        customer_billable_hours = frappe.db.sql("""
            SELECT SUM((actual_time * percent_billable / 100) / 3600)
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND project NOT IN (%s, %s)
            AND docstatus = '1'
        """, (month_start, month_end, "PROJ-0055", "P-0230"))[0][0] or 0

        # Delivery Note Hrs
        delivery_note_hrs = frappe.db.sql("""
            SELECT SUM(total_qty)
            FROM `tabDelivery Note`
            WHERE posting_date >= %s AND posting_date <= %s
        """, (month_start, month_end))[0][0] or 0

        # Invoiced Hrs
        invoiced_hrs = frappe.db.sql("""
            SELECT SUM(sii.qty)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date >= %s AND si.posting_date <= %s
        """, (month_start, month_end))[0][0] or 0

        # Paid Invoiced Hrs
        paid_invoiced_hrs = frappe.db.sql("""
            SELECT SUM(sii.qty)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date >= %s AND si.posting_date <= %s
            AND si.status = 'Paid'
        """, (month_start, month_end))[0][0] or 0

        # Invoiced Amount
        amount_invoiced = frappe.db.sql("""
            SELECT SUM(sii.amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date >= %s AND si.posting_date <= %s
        """, (month_start, month_end))[0][0] or 0

        # Paid Amount
        amount_recieved = frappe.db.sql("""
            SELECT SUM(sii.amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date >= %s AND si.posting_date <= %s
            AND si.status = 'Paid'
        """, (month_start, month_end))[0][0] or 0

        row = [
            month_name,
            round(total_hours, 2),
            round(customer_hours, 2),
            round(customer_billable_hours, 2),
            round(delivery_note_hrs, 2),
            round(invoiced_hrs, 2),
            round(paid_invoiced_hrs, 2),
            round(amount_invoiced, 2),
            round(amount_recieved, 2)
        ]

        # Add row to data
        data.append(row)

        # Accumulate quarterly totals (skip month name column)
        for i in range(8):
            quarter_totals[i] += row[i + 1]

        # Every 3rd month (March, June, Sep, Dec), add quarter total
        if month % 3 == 0:
            quarter_label = f"Q{month // 3}"
            total_row = add_quarter_row(quarter_label)
            total_row = ["<b>" + str(col) + "</b>" if isinstance(col, str) else col for col in total_row]
            data.append(total_row)
            quarter_totals = [0] * 8  # Reset for next quarter

    columns = [
        {"label": "Month", "fieldname": "month", "fieldtype": "Data", "width": 150},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 150, "precision": 2},
        {"label": "Total Customer Hrs", "fieldname": "customer_hours", "fieldtype": "Float", "width": 180, "precision": 2},
        {"label": "Total Customer Billable Hrs", "fieldname": "billable_hours", "fieldtype": "Float", "width": 220, "precision": 2},
        {"label": "Delivery Note Hrs", "fieldname": "delivery_note_hrs", "fieldtype": "Float", "width": 180, "precision": 2},
        {"label": "Invoiced Hrs", "fieldname": "invoiced_hrs", "fieldtype": "Float", "width": 180, "precision": 2},
        {"label": "Paid Invoiced Hrs", "fieldname": "paid_invoiced_hrs", "fieldtype": "Float", "width": 200, "precision": 2},
        {"label": "Invoiced € Net", "fieldname": "amount_invoiced", "fieldtype": "Currency", "width": 180, "precision": 2},
        {"label": "Paid € Gross", "fieldname": "amount_recieved", "fieldtype": "Currency", "width": 200, "precision": 2}
    ]

    return columns, data
