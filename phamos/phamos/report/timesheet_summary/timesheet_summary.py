# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    # Crucial: Handle empty filter to prevent SQL crash
    if not filters.get("time_period"):
        filters["time_period"] = "Last 6 Months"

    columns = [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Data", "width": 200},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Total Billable Hours", "fieldname": "total_billable_hours", "fieldtype": "Float", "width": 150}
    ]

    # Note: Using %s or %(key)s works, but let's ensure the dictionary is passed
    data = frappe.db.sql("""
        SELECT
            employee,
            employee_name,
            SUM(total_hours) as total_hours,
            SUM(total_billable_hours) as total_billable_hours
        FROM
            `tabTimesheet`
        WHERE
            docstatus < 2
            AND (
                CASE 
                    WHEN %(time_period)s = 'Last Week' THEN start_date >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK)
                    WHEN %(time_period)s = 'Last 2 Weeks' THEN start_date >= DATE_SUB(CURDATE(), INTERVAL 2 WEEK)
                    WHEN %(time_period)s = 'Last Month' THEN start_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
                    WHEN %(time_period)s = 'Last 3 Months' THEN start_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                    WHEN %(time_period)s = 'Last 6 Months' THEN start_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                    ELSE 1=1 
                END
            )
        GROUP BY
            employee
    """, filters, as_dict=1)

    return columns, data