# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    year = int(filters.get("year") or frappe.utils.nowdate().split("-")[0])

    data = []
    quarter_totals = [0] * 8
    yearly_totals = [0] * 8

    def add_quarter_row(qtr_label):
        return [f"{qtr_label} Total"] + [round(val, 2) for val in quarter_totals]


    for month in range(1, 13):
        month_name = frappe.utils.formatdate(f"{year}-{month:02d}-01", "MMMM")
        month_start = f"{year}-{month:02d}-01"
        month_end = frappe.utils.get_last_day(month_start)

        total_hours = frappe.db.sql("""
            SELECT SUM(actual_time)/3600
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND docstatus = 1
        """, (month_start, month_end))[0][0] or 0

        customer_hours = frappe.db.sql("""
            SELECT SUM(actual_time)/3600
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND project NOT IN (%s, %s)
            AND docstatus = 1
        """, (month_start, month_end, "PROJ-0055", "P-0230"))[0][0] or 0

        customer_billable_hours = frappe.db.sql("""
            SELECT SUM((actual_time * percent_billable / 100) / 3600)
            FROM `tabTimesheet Record`
            WHERE from_time >= %s AND to_time <= %s
            AND project NOT IN (%s, %s)
            AND docstatus = 1
        """, (month_start, month_end, "PROJ-0055", "P-0230"))[0][0] or 0

        delivery_note_hrs = frappe.db.sql("""
            SELECT SUM(total_qty)
            FROM `tabDelivery Note`
            WHERE posting_date BETWEEN %s AND %s
        """, (month_start, month_end))[0][0] or 0

        invoiced_hrs = frappe.db.sql("""
            SELECT SUM(sii.qty)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date BETWEEN %s AND %s
        """, (month_start, month_end))[0][0] or 0

        paid_invoiced_hrs = frappe.db.sql("""
            SELECT SUM(sii.qty)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date BETWEEN %s AND %s
            AND si.status = 'Paid'
        """, (month_start, month_end))[0][0] or 0

        amount_invoiced = frappe.db.sql("""
            SELECT SUM(sii.amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date BETWEEN %s AND %s
        """, (month_start, month_end))[0][0] or 0

        amount_received = frappe.db.sql("""
            SELECT SUM(sii.amount)
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON sii.parent = si.name
            WHERE si.posting_date BETWEEN %s AND %s
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
            round(amount_received, 2)
        ]

        data.append(row)

        for i in range(8):
            quarter_totals[i] += row[i + 1]
            yearly_totals[i] += row[i + 1]

        if month % 3 == 0:
            data.append(add_quarter_row(f"Q{month // 3}"))
            quarter_totals = [0] * 8

    data.append(
        ["Grand Total"]
        + [round(val, 2) for val in yearly_totals]
    )

    columns = [
        {"label": "Month", "fieldtype": "Data", "width": 150},
        {"label": "Total Hours", "fieldtype": "Float", "width": 150},
        {"label": "Total Customer Hrs", "fieldtype": "Float", "width": 180},
        {"label": "Customer Billable Hrs", "fieldtype": "Float", "width": 220},
        {"label": "Delivery Note Hrs", "fieldtype": "Float", "width": 180},
        {"label": "Invoiced Hrs", "fieldtype": "Float", "width": 180},
        {"label": "Paid Invoiced Hrs", "fieldtype": "Float", "width": 200},
        {"label": "Invoiced € Net", "fieldtype": "Currency", "width": 180},
        {"label": "Paid € Gross", "fieldtype": "Currency", "width": 200},
    ]

    return columns, data
