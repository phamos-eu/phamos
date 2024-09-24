import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime,time_diff,today
from frappe.utils.data import add_to_date,format_duration, time_diff_in_seconds
from datetime import datetime
from datetime import datetime, timedelta

@frappe.whitelist()
def create_timesheet_record(project_name,  customer, from_time, expected_time, goal,task=None):
    try:
        employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
        activity_type = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "activity_type")
        customer = frappe.db.get_value("Customer", {"customer_name": customer}, "name")
        project = frappe.db.get_value("Project", {"project_name": project_name}, "name")
        
        if employee_name:
            after_1_minute = add_to_date(from_time, seconds=10, as_string=True)
            
            timesheet_record = frappe.new_doc('Timesheet Record')
            timesheet_record.project = project
            timesheet_record.task=task
            timesheet_record.customer = customer
            timesheet_record.from_time = after_1_minute
            timesheet_record.expected_time = expected_time
            timesheet_record.goal = goal
            timesheet_record.employee = employee_name
            timesheet_record.activity_type = activity_type

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
def update_and_submit_timesheet_record(name, to_time,percent_billable,activity_type, result,task=None):
    try:
        # Retrieve the Timesheet Record document
        doc = frappe.get_doc("Timesheet Record", name)
        to_time_add_seconds = add_to_date(to_time, seconds=20, as_string=True)
        
        # Update the fields
        doc.to_time = to_time_add_seconds
        doc.task = task
        doc.activity_type = activity_type
        doc.result = result
        doc.actual_time = time_diff_in_seconds(doc.to_time, doc.from_time)
        doc.percent_billable = percent_billable
         
        
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
        SELECT p.percent_billable as percent_billable ,p.name AS name, p.planned_hours AS planned_hours, p.status AS status, p.notes AS notes, p.project_name AS project_name, CONCAT(p.name, " - ", p.project_name) AS project_desc,
        ROUND((SELECT SUM(t.total_hours) FROM `tabTimesheet` t 
        WHERE t.docstatus = 0 and t.employee = %(employee)s AND t.name IN (SELECT td.parent FROM `tabTimesheet Detail` td WHERE td.project = p.name)), 3) AS spent_hours_draft,
        ROUND((SELECT SUM(t.total_hours) FROM `tabTimesheet` t 
        WHERE t.docstatus = 1 and t.employee = %(employee)s AND t.name IN (SELECT td.parent FROM `tabTimesheet Detail` td WHERE td.project = p.name)), 3) AS spent_hours_submitted,
        (SELECT name FROM `tabCustomer` c WHERE p.customer = c.name) AS customer,
        (SELECT CASE WHEN c.name != c.customer_name THEN CONCAT(c.name, " - ", c.customer_name) ELSE c.customer_name END FROM `tabCustomer` c WHERE p.customer = c.name) AS customer_desc,
        (SELECT max(ts.name) FROM `tabTimesheet Record` ts WHERE ts.project = p.name AND ts.employee = %(employee)s AND ts.docstatus = 0) AS timesheet_record,
        (SELECT (ts1.task) FROM `tabTimesheet Record` ts1 WHERE ts1.name = (SELECT max(ts.name) FROM `tabTimesheet Record` ts WHERE ts.project = p.name AND ts.employee = %(employee)s AND ts.docstatus = 0)) AS task
        FROM `tabProject` p
        WHERE (SELECT max(reference_name) FROM `tabToDo` td WHERE td.status = "Open" AND td.reference_name = p.name AND td.allocated_to = %(user)s) IS NOT NULL
        ORDER BY timesheet_record IS NULL, timesheet_record ASC  # Show records with timesheet_record first
    """, {"employee": employee_name, "user": frappe.session.user}, as_dict=True)

    # Return project data
    return projects




@frappe.whitelist()
def get_permitted_cards(dashboard_name):
	permitted_cards = []
	dashboard = frappe.get_doc("Dashboard", dashboard_name)
	for card in dashboard.cards:
		if frappe.has_permission("Number Card", doc=card.card):
			permitted_cards.append(card)
	return permitted_cards

@frappe.whitelist()
def get_project_count():
    count_projects = frappe.db.sql("""
        SELECT count(p.name) AS total_projects
        FROM `tabProject` p
        WHERE (SELECT max(reference_name) FROM `tabToDo` td WHERE td.status = "Open" and td.reference_name = p.name and td.allocated_to = %(user)s) IS NOT NULL
    """, {"user": frappe.session.user}, as_dict=True)

    return {
        "value": count_projects[0].get('total_projects') if count_projects else 0 , # assuming you want to return the count of projects meeting certain conditions,
        "fieldtype": "Int",
        #"count_projects": count_projects[0].get('total_projects') if count_projects else 0  # assuming you want to return the count of projects meeting certain conditions
    }


@frappe.whitelist()
def total_hours_worked_today():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date
    count_time = frappe.db.sql("""
        SELECT sum(ts.actual_time) AS actual_time
        FROM `tabTimesheet Record` ts
        WHERE ts.employee = %(employee)s AND DATE(ts.from_time) = %(today_date)s
    """, {"employee": employee_name, "today_date": today_date}, as_dict=True)
    
    if count_time and count_time[0].actual_time:
        actual_time = format_duration(count_time[0].actual_time)
        actual_time_str = str(actual_time)[:9]
        #frappe.msgprint(f"Total hours worked today: {actual_time_str}")
        
        return {
            "value": actual_time_str,
            "fieldtype": "Float"
        }
    else:
        actual_time_str = 0
        return {
            "value": actual_time_str,
            "fieldtype": "Float"
        }



@frappe.whitelist()
def total_hours_worked_in_this_week():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date
    start_of_week = today_date - timedelta(days=today_date.weekday())  # Calculate the start of the current week
    end_of_week = start_of_week + timedelta(days=6)  # Calculate the end of the current week

    count_time = frappe.db.sql("""
        SELECT SUM(ts.actual_time) AS total_actual_time
        FROM `tabTimesheet Record` ts
        WHERE ts.employee = %(employee)s 
        AND ts.from_time BETWEEN %(start_of_week)s AND %(end_of_week)s
    """, {"employee": employee_name, "start_of_week": start_of_week, "end_of_week": end_of_week}, as_dict=True)
    
    if count_time and count_time[0].total_actual_time:
        total_actual_time = format_duration(count_time[0].total_actual_time)
        total_actual_time_str = str(total_actual_time)[:10]
        #frappe.msgprint(f"Total hours worked this week: {total_actual_time_str}")
        
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float"
        }
    else:
        total_actual_time_str = 0
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float"
        }


@frappe.whitelist()
def total_hours_worked_in_this_month():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date
    start_of_month = today_date.replace(day=1)  # Calculate the start of the current month
    next_month = start_of_month.replace(month=start_of_month.month + 1)  # Calculate the start of the next month
    end_of_month = next_month - timedelta(days=1)  # Calculate the end of the current month

    count_time = frappe.db.sql("""
        SELECT SUM(ts.actual_time) AS total_actual_time
        FROM `tabTimesheet Record` ts
        WHERE ts.employee = %(employee)s 
        AND ts.from_time BETWEEN %(start_of_month)s AND %(end_of_month)s
    """, {"employee": employee_name, "start_of_month": start_of_month, "end_of_month": end_of_month}, as_dict=True)
     
    if count_time and count_time[0].total_actual_time:
        total_actual_time = format_duration(count_time[0].total_actual_time)
        total_actual_time_str = str(total_actual_time)[:10]
        #frappe.msgprint(f"Total hours worked this month: {total_actual_time_str}")
        
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float"
        }
    else:
        total_actual_time_str = 0
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float"
        }


def format_duration(duration_in_seconds):
	minutes, seconds = divmod(duration_in_seconds, 60)
	hours, minutes = divmod(minutes, 60)
	if hours > 0:
		return f"{hours} Hrs {minutes} Mins"
	elif minutes > 0:
		return f"{minutes} Mins"
	else:
		return f"{seconds} Secs"