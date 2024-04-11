import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime


@frappe.whitelist()
def create_timesheet_record(project_name,customer, activity_type,percent_billable, from_time, expected_time, goal):
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    customer = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
    project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    
    if employee_name:
        timesheet_record = frappe.new_doc('Timesheet Record')

        timesheet_record.project = project
        timesheet_record.customer = customer
        timesheet_record.activity_type = activity_type
        timesheet_record.from_time = from_time
        timesheet_record.expected_time = expected_time
        timesheet_record.goal = goal
        timesheet_record.percent_billable = percent_billable
        timesheet_record.employee = employee_name

        timesheet_record.save()

        return timesheet_record
    else:
        frappe.throw("Employee not found for the current user.")

# In your Python script, within @frappe.whitelist()
@frappe.whitelist()
def update_and_submit_timesheet_record(name, to_time, result):
    # Retrieve the Timesheet Record document
    doc = frappe.get_doc("Timesheet Record", name)
    
    # Update the fields
    doc.to_time = to_time
    doc.result = result
    doc.actual_time = time_diff_in_seconds(doc.to_time, doc.from_time)
    
    # Save the changes
    doc.save()
    
    # Submit the document
    doc.submit()
    
    # Optionally, return any response you need
    return "Timesheet Record updated and submitted successfully"


@frappe.whitelist(allow_guest=True)
def get_employee_and_project(project_name):
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
    timesheet_record = frappe.db.get_value("Timesheet Record", {"project": project,"employee":employee,"docstatus":0}, "name")
    return employee,project,timesheet_record

@frappe.whitelist()
def check_draft_timesheet_record():
    try:
        # Fetch employee name
        employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        
        # Fetch draft Timesheet Records
        timesheet_record_drafts = frappe.db.sql("""
            SELECT name as timesheet_record_draft
            FROM `tabTimesheet Record`
            WHERE employee = %(employee)s AND docstatus = 0
        """, {"employee": employee_name}, as_dict=True)

        # Return draft Timesheet Records
        return timesheet_record_drafts
    except Exception as e:
        frappe.log_error(f"Error in check_draft_timesheet_record: {e}")
        return None
    
@frappe.whitelist()
def fetch_projects():
    # Custom SQL query to fetch project data
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    projects = frappe.db.sql("""
        SELECT p.name AS name, p.status AS status, p.notes AS notes, p.project_name AS project_name,
            (SELECT customer_name FROM `tabCustomer` c WHERE p.customer = c.name) AS customer,
            (SELECT max(ts.name) FROM `tabTimesheet Record` ts WHERE ts.project = p.name and ts.employee = %(employee)s and ts.docstatus = 0) AS timesheet_record
        FROM `tabProject` p
    """, {"employee": employee_name}, as_dict=True)

    # Return project data
    return projects

