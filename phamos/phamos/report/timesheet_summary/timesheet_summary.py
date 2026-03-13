# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime, timedelta

def execute(filters=None):
    if not filters:
        filters = {}

    columns = [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Data", "width": 160},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Total Billable Hours", "fieldname": "total_billable_hours", "fieldtype": "Float", "width": 150},
        {"label": "Leave Days", "fieldname": "total_leave_days", "fieldtype": "Float", "width": 120},
        {"label": "Half Days", "fieldname": "half_day_count", "fieldtype": "Int", "width": 100}
    ]

    # Use get_date_range to determine start_date and end_date
    start_date, end_date = get_date_range(filters)

    # 1. Fetch Timesheet Data
    timesheet_data = frappe.db.sql("""
        SELECT
            employee,
            employee_name,
            SUM(total_hours) as total_hours,
            SUM(total_billable_hours) as total_billable_hours
        FROM `tabTimesheet`
        WHERE docstatus < 2
        {date_filter}
        GROUP BY employee
    """.format(
        date_filter="AND start_date >= %(start_date)s AND start_date <= %(end_date)s" if start_date and end_date else ""
    ), {"start_date": start_date, "end_date": end_date}, as_dict=1)

    # 2. Fetch Leave Application Data
    leave_data = frappe.db.sql("""
        SELECT
            employee,
            SUM(total_leave_days) as total_leave_days,
            SUM(CASE WHEN half_day = 1 THEN 1 ELSE 0 END) as half_day_count
        FROM `tabLeave Application`
        WHERE docstatus = 1 AND status = 'Approved'
        {date_filter}
        GROUP BY employee
    """.format(
        date_filter="AND from_date >= %(start_date)s AND from_date <= %(end_date)s" if start_date and end_date else ""
    ), {"start_date": start_date, "end_date": end_date}, as_dict=1)

    # 3. Merge Data into a single report
    leave_map = {d.employee: d for d in leave_data}
    all_employees = set([d.employee for d in timesheet_data] + [d.employee for d in leave_data])
    employee_names = {d.employee: d.employee_name for d in timesheet_data}
    report_data = []
    for emp in all_employees:
        ts = next((x for x in timesheet_data if x.employee == emp), {})
        lv = leave_map.get(emp, {})
        name = employee_names.get(emp) or frappe.db.get_value("Employee", emp, "employee_name")
        report_data.append({
            "employee": emp,
            "employee_name": name,
            "total_hours": ts.get("total_hours", 0),
            "total_billable_hours": ts.get("total_billable_hours", 0),
            "total_leave_days": lv.get("total_leave_days", 0),
            "half_day_count": lv.get("half_day_count", 0)
        })
    report_data.sort(key=lambda x: x['employee_name'] or "")
    return columns, report_data

def get_date_range(filters):
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

    return start_date, end_date