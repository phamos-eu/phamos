# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate
from frappe.utils import get_datetime_str


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data

def get_columns():
    return [
        {"label": "Start Time", "fieldname": "from_time", "fieldtype": "Datetime", "width": 180},
        {"label": "End Time", "fieldname": "to_time", "fieldtype": "Datetime", "width": 180},
        {"label": "CReation", "fieldname": "creation", "fieldtype": "Datetime", "width": 180},
        {"label": "Project", "fieldname": "project", "fieldtype": "Link", "options": "Project", "width": 120},
        {"label": "Timesheet Record", "fieldname": "name", "fieldtype": "Link", "options": "Timesheet Record", "width": 150},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 150},
        {"label": "Employee", "fieldname": "employee", "fieldtype": "Link", "options": "Employee", "width": 150},
        {"label": "Percent Billable", "fieldname": "percent_billable", "fieldtype": "Data", "width": 120},
        {"label": "Timesheet Record Color", "fieldname": "timesheet_record_color", "fieldtype": "Data", "width": 100},
    ]

def get_data(filters):
    conditions = ""
    from frappe.utils import get_datetime_str
    if filters.get("from_date"):
          conditions += f" AND from_time >= '{get_datetime_str(filters.get('from_date'))}'"
    if filters.get("to_date"):
          to_date = filters.get('to_date') + ' 23:59:59'
          conditions += f" AND to_time <= '{to_date}'"


    if filters.get("customer"):
        conditions += f" AND customer = '{filters.get('customer')}'"
    if filters.get("employee"):
        conditions += f" AND employee = '{filters.get('employee')}'"

    return frappe.db.sql(f"""
        SELECT 
            from_time,
            to_time,
            creation,
            project,
            name,
            customer,
            employee,
            percent_billable,
            timesheet_record_color
        FROM `tabTimesheet Record`
        WHERE docstatus = 1
        {conditions}
    """, as_dict=True)

