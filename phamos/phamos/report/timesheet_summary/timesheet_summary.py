# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe

def execute(filters=None):
    if not filters:
        filters = {}

    if not filters.get("time_period"):
        filters["time_period"] = "Last 6 Months"

    columns = [
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Data", "width": 160},
        {"label": "Employee Name", "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": "Total Hours", "fieldname": "total_hours", "fieldtype": "Float", "width": 120},
        {"label": "Total Billable Hours", "fieldname": "total_billable_hours", "fieldtype": "Float", "width": 150},
        {"label": "Leave Days", "fieldname": "total_leave_days", "fieldtype": "Float", "width": 120},
        {"label": "Half Days", "fieldname": "half_day_count", "fieldtype": "Int", "width": 100}
    ]

    # 1. Fetch Timesheet Data
    timesheet_data = frappe.db.sql("""
        SELECT
            employee,
            employee_name,
            SUM(total_hours) as total_hours,
            SUM(total_billable_hours) as total_billable_hours
        FROM `tabTimesheet`
        WHERE docstatus < 2
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
        GROUP BY employee
    """, filters, as_dict=1)

    # 2. Fetch Leave Application Data
    # Note: We use 'from_date' for the leave filter to match your 'start_date' logic
    leave_data = frappe.db.sql("""
        SELECT
            employee,
            SUM(total_leave_days) as total_leave_days,
            SUM(CASE WHEN half_day = 1 THEN 1 ELSE 0 END) as half_day_count
        FROM `tabLeave Application`
        WHERE docstatus = 1 AND status = 'Approved'
        AND (
            CASE 
                WHEN %(time_period)s = 'Last Week' THEN from_date >= DATE_SUB(CURDATE(), INTERVAL 1 WEEK)
                WHEN %(time_period)s = 'Last 2 Weeks' THEN from_date >= DATE_SUB(CURDATE(), INTERVAL 2 WEEK)
                WHEN %(time_period)s = 'Last Month' THEN from_date >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
                WHEN %(time_period)s = 'Last 3 Months' THEN from_date >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
                WHEN %(time_period)s = 'Last 6 Months' THEN from_date >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                ELSE 1=1 
            END
        )
        GROUP BY employee
    """, filters, as_dict=1)

    # 3. Merge Data into a single report
    # Map leave data by employee for easy access
    leave_map = {d.employee: d for d in leave_data}
    
    # We want to show employees who have EITHER timesheets OR leaves
    all_employees = set([d.employee for d in timesheet_data] + [d.employee for d in leave_data])
    
    # Pre-fetch employee names for those who might only have leaves
    employee_names = {d.employee: d.employee_name for d in timesheet_data}
    
    report_data = []
    for emp in all_employees:
        ts = next((x for x in timesheet_data if x.employee == emp), {})
        lv = leave_map.get(emp, {})
        
        # If employee name isn't in timesheet data, get it from DB
        name = employee_names.get(emp) or frappe.db.get_value("Employee", emp, "employee_name")

        report_data.append({
            "employee": emp,
            "employee_name": name,
            "total_hours": ts.get("total_hours", 0),
            "total_billable_hours": ts.get("total_billable_hours", 0),
            "total_leave_days": lv.get("total_leave_days", 0),
            "half_day_count": lv.get("half_day_count", 0)
        })

    # Sort by Employee Name
    report_data.sort(key=lambda x: x['employee_name'] or "")

    return columns, report_data