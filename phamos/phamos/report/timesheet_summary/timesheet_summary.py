# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    from datetime import datetime, timedelta

    columns = get_columns()
    data = []

    if not filters:
        return columns, data

    range_type = filters.get("range_type")
    if range_type == "Timespan":
        time_period = filters.get("time_period")
        end_date = datetime.today().date()
        if time_period == "Last Week":
            start_date = end_date - timedelta(days=7)
        elif time_period == "Last 2 Weeks":
            start_date = end_date - timedelta(days=14)
        elif time_period == "Last Month":
            start_date = end_date - timedelta(days=30)
        elif time_period == "Last 3 Months":
            start_date = end_date - timedelta(days=90)
        elif time_period == "Last 6 Months":
            start_date = end_date - timedelta(days=180)
        else:
            start_date = None
    elif range_type == "Between":
        start_date = filters.get("start_date")
        end_date = filters.get("end_date")
    else:
        start_date = end_date = None

    # Use start_date and end_date in your query logic
    # Example:
    # data = frappe.db.sql("""
    #     SELECT ... FROM ... WHERE date BETWEEN %s AND %s
    # """, (start_date, end_date))

    return columns, data

def get_columns():
    return [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Data", "width": 160},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Total Billable Hours", "fieldname": "total_billable_hours", "fieldtype": "Float", "width": 150},
        {"label": "Leave Days", "fieldname": "total_leave_days", "fieldtype": "Float", "width": 120},
        {"label": "Half Days", "fieldname": "half_day_count", "fieldtype": "Int", "width": 100}
    ]