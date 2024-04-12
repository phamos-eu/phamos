import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime
from frappe.utils.data import add_to_date
from datetime import datetime

@frappe.whitelist()
def create_timesheet_record(project_name, customer, activity_type, percent_billable, from_time, expected_time, goal):
    try:
        employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        customer = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
        project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
        
        if employee_name:
            after_1_minute = add_to_date(from_time, minutes=1, as_string=True)
            
            timesheet_record = frappe.new_doc('Timesheet Record')
            timesheet_record.project = project
            timesheet_record.customer = customer
            timesheet_record.activity_type = activity_type
            timesheet_record.from_time = after_1_minute
            timesheet_record.expected_time = expected_time
            timesheet_record.goal = goal
            timesheet_record.percent_billable = percent_billable
            timesheet_record.employee = employee_name

            timesheet_record.save()
            
            # Return the saved timesheet record
            return timesheet_record
        else:
            frappe.throw("Employee not found for the current user.")
    except Exception as e:
        # Handle errors here, you can log the error for further investigation
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Creation Error")
        
        # Return None or an error message to indicate the failure
        return None

# In your Python script, within @frappe.whitelist()
@frappe.whitelist()
def update_and_submit_timesheet_record(name, to_time, result):
    try:
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
        
        # Return success message if update and submission were successful
        return "Timesheet Record updated and submitted successfully"
    
    except Exception as e:
        # Handle errors here, you can log the error for further investigation
        frappe.log_error(frappe.get_traceback(), "Timesheet Record Update and Submit Error")
        
        # Return error message
        return "Error: Failed to update and submit Timesheet Record. Please try again or contact your administrator."



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
        WHERE (SELECT max(reference_name) FROM `tabToDo` td WHERE td.reference_name = p.name and td.allocated_to = %(user)s) IS NOT NULL
    """, {"employee": employee_name, "user": frappe.session.user}, as_dict=True)

    # Return project data
    return projects
