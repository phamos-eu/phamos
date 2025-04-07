import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cstr, now_datetime, time_diff_in_seconds, get_datetime,time_diff,today
from frappe.utils.data import add_to_date,format_duration, time_diff_in_seconds
from datetime import datetime
from datetime import datetime, timedelta
from frappe.query_builder import Field, Case, Order, DocType, functions as fn
from frappe.query_builder.functions import Concat, Max, Sum, Round, Coalesce, IfNull

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
    # Get Employee linked to current user
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee_name:
        frappe.throw("Employee not found for the current user.")

    # Define DocTypes
    Project = DocType("Project")
    Timesheet = DocType("Timesheet")
    TimesheetDetail = DocType("Timesheet Detail")
    Customer = DocType("Customer")
    TimesheetRecord = DocType("Timesheet Record")
    ToDo = DocType("ToDo")

    # Subqueries for calculations
    spent_hours_draft = (
        frappe.qb.from_(Timesheet)
        .select(Coalesce(Sum(Timesheet.total_hours), 0))
        .where(
            (Timesheet.docstatus == 0)
            & (Timesheet.employee == employee_name)
            & (Timesheet.name.isin(
                frappe.qb.from_(TimesheetDetail)
                .select(TimesheetDetail.parent)
                .where(TimesheetDetail.project == Project.name)
            ))
        )
    )

    spent_hours_submitted = (
        frappe.qb.from_(Timesheet)
        .select(Coalesce(Sum(Timesheet.total_hours), 0))
        .where(
            (Timesheet.docstatus == 1)
            & (Timesheet.employee == employee_name)
            & (Timesheet.name.isin(
                frappe.qb.from_(TimesheetDetail)
                .select(TimesheetDetail.parent)
                .where(TimesheetDetail.project == Project.name)
            ))
        )
    )

    latest_timesheet_record = (
        frappe.qb.from_(TimesheetRecord)
        .select(Max(TimesheetRecord.name))
        .where(
            (TimesheetRecord.project == Project.name)
            & (TimesheetRecord.employee == employee_name)
            & (TimesheetRecord.docstatus == 0)
        )
    )

    latest_task = (
        frappe.qb.from_(TimesheetRecord)
        .select(TimesheetRecord.task)
        .where(TimesheetRecord.name == latest_timesheet_record)
    )

    last_timesheet_update = (
        frappe.qb.from_(TimesheetRecord)
        .select(Max(TimesheetRecord.creation))
        .where(
            (TimesheetRecord.project == Project.name)
            & (TimesheetRecord.employee == employee_name)
        )
    )

    # Handling Customer Description (Replacing CASE)
    customer_desc_query = IfNull(Customer.customer_name, Customer.name)

    # Main Query
    query = (
        frappe.qb.from_(Project)
        .left_join(Customer).on(Customer.name == Project.customer)
        .select(
            Project.percent_billable,
            Project.name.as_("name"),
            Project.planned_hours,
            Project.task_in_timesheet_record,
            Project.status,
            Project.notes,
            Project.project_name,
            Concat(Project.name, " - ", Project.project_name).as_("project_desc"),
            Round(spent_hours_draft, 3).as_("spent_hours_draft"),
            Round(spent_hours_submitted, 3).as_("spent_hours_submitted"),
            Customer.name.as_("customer"),
            customer_desc_query.as_("customer_desc"),
            latest_timesheet_record.as_("timesheet_record"),
            latest_task.as_("task"),
            last_timesheet_update.as_("last_timesheet_update"),
        )
        .where(
            frappe.qb.from_(ToDo)
            .select(Max(ToDo.reference_name))
            .where(
                (ToDo.status == "Open")
                & (ToDo.reference_name == Project.name)
                & (ToDo.allocated_to == frappe.session.user)
            ).isnotnull()
        )
        .orderby(Coalesce(last_timesheet_update, "1970, 1, 1"), order=Order.desc)
        
    )
    # Execute query
    projects = query.run(as_dict=True)
    return projects

@frappe.whitelist()
def fetch_all_projects():
    project = frappe.qb.DocType("Project")
    customer = frappe.qb.DocType("Customer")
    todo = frappe.qb.DocType("ToDo")

    customer_subquery = (
        frappe.qb.from_(customer)
        .select(
            (
                Case()
                .when(customer.name != customer.customer_name, Concat(customer.name, " - ", customer.customer_name))
                .else_(customer.customer_name)
            ).as_("customer_desc")
        )
        .where(customer.name == project.customer)
        )

    todo_subquery = (
        frappe.qb.from_(todo)
        .select(todo.reference_name)
        .where(
            (todo.status == "Open") &
            (todo.allocated_to == frappe.session.user)
        )
        )

    projects = (
        frappe.qb.from_(project)
        .select(
            project.name.as_("name"),
            project.status.as_("status"),
            project.project_name.as_("project_name"),
            Concat(project.name, " - ", project.project_name).as_("project_desc"),
            project.customer.as_("customer"),
            customer_subquery.as_("customer_desc")
        )
        .where(
            (project.status == "Open") &
            (project.name.notin(todo_subquery)) 
        )
        ).run(as_dict=True)
 
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
def get_project_count_all():
    count_projects = frappe.db.sql("""
        SELECT count(p.name) AS total_projects
        FROM `tabProject` p
    """, {}, as_dict=True)

    return {
        "value": count_projects[0].get('total_projects') if count_projects else 0 , # assuming you want to return the count of projects meeting certain conditions,
        "fieldtype": "Int",
        #"count_projects": count_projects[0].get('total_projects') if count_projects else 0  # assuming you want to return the count of projects meeting certain conditions
    }

@frappe.whitelist()
def total_hours_worked_today():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date
    TimesheetRecord = DocType("Timesheet Record")
    count_time = (
        frappe.qb.from_(TimesheetRecord)
        .select(
            fn.Sum(TimesheetRecord.actual_time).as_("actual_time"),
            fn.Sum(TimesheetRecord.actual_time * TimesheetRecord.percent_billable / 100).as_("total_billable_time")
        )
        .where(
            (TimesheetRecord.employee == employee_name)
            & (fn.Date(TimesheetRecord.from_time) == today_date)
        )
        .run(as_dict=True)
    )

    if count_time and count_time[0].actual_time:
        # Format actual time
        actual_time = format_duration(count_time[0].actual_time)
        actual_time_str = str(actual_time)[:9]

        # Format billable time if it exists
        total_billable_time = count_time[0].total_billable_time
        total_billable_time_str = 0
        if total_billable_time:
            total_billable_time = format_duration(total_billable_time)
            total_billable_time_str = str(total_billable_time)[:10]
        
        return {
            "value": actual_time_str,
            "fieldtype": "Float",
            "billable": total_billable_time_str
        }
    else:
        # If no time was worked, return zero
        return {
            "value": 0,
            "fieldtype": "Float",
            "billable": 0
        }

@frappe.whitelist()
def total_hours_worked_in_this_week():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date
    start_of_week = today_date - timedelta(days=today_date.weekday())  # Calculate the start of the current week
    end_of_week = start_of_week + timedelta(days=6)  # Calculate the end of the current week

    TimesheetRecord = DocType("Timesheet Record")
    count_time = (
        frappe.qb.from_(TimesheetRecord)
        .select(
            fn.Sum(TimesheetRecord.actual_time).as_("total_actual_time"),
            fn.Sum(TimesheetRecord.actual_time * TimesheetRecord.percent_billable / 100).as_("total_billable_time")
        )
        .where(
            (TimesheetRecord.employee == employee_name)
            & (TimesheetRecord.from_time.between(start_of_week, end_of_week))
        )
        .run(as_dict=True)
    )

    if count_time and count_time[0].total_actual_time:
        total_actual_time = format_duration(count_time[0].total_actual_time)
        total_actual_time_str = str(total_actual_time)[:10]

        # Format billable time
        total_billable_time = count_time[0].total_billable_time
        total_billable_time_str = 0
        if total_billable_time:
            total_billable_time = format_duration(total_billable_time)
            total_billable_time_str = str(total_billable_time)[:10]
        
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float",
            "billable": total_billable_time_str
        }
    else:
        return {
            "value": 0,
            "fieldtype": "Float",
            "billable": 0
        }

@frappe.whitelist()
def total_hours_worked_in_this_month():
    employee_name = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    today_date = datetime.today().date()  # Get today's date

    start_of_month = today_date.replace(day=1)  # Calculate the start of the current month
    
    if start_of_month.month == 12: 
        next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
    else:    
        next_month = start_of_month.replace(month=start_of_month.month + 1)  # Calculate the start of the next month
    end_of_month = next_month - timedelta(days=1)  # Calculate the end of the current month

    TimesheetRecord = DocType("Timesheet Record")
    count_time = (
        frappe.qb.from_(TimesheetRecord)
        .select(
            fn.Sum(TimesheetRecord.actual_time).as_("total_actual_time"),
            fn.Sum(TimesheetRecord.actual_time * TimesheetRecord.percent_billable / 100).as_("total_billable_time")
        )
        .where(
            (TimesheetRecord.employee == employee_name)
            & (TimesheetRecord.from_time.between(start_of_month, end_of_month))
        )
        .run(as_dict=True)
    )

    if count_time and count_time[0].total_actual_time:
        total_actual_time = format_duration(count_time[0].total_actual_time)
        total_actual_time_str = str(total_actual_time)[:10]

        # Format billable time
        total_billable_time = count_time[0].total_billable_time
        total_billable_time_str = 0
        if total_billable_time:
            total_billable_time = format_duration(total_billable_time)
            total_billable_time_str = str(total_billable_time)[:10]
        
        return {
            "value": total_actual_time_str,
            "fieldtype": "Float",
            "billable": total_billable_time_str
        }
    else:
        return {
            "value": 0,
            "fieldtype": "Float",
            "billable": 0
        }

def format_duration(duration_in_seconds):
    minutes, seconds = divmod(duration_in_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{int(hours)} Hrs"
    elif minutes > 0:
        return f"{int(minutes)} Mins"
    else:
        return f"{int(seconds)} Secs"


@frappe.whitelist()
def set_actual_time(from_time, to_time):
	if from_time and to_time:
		return time_diff_in_seconds(to_time, from_time)
     
@frappe.whitelist()
def self_assign_project(project_name):
    try:
        # Fetch the current employee name linked to the logged-in user
        employee_name = frappe.get_cached_value("Employee", {"user_id": frappe.session.user}, "employee_name")
        
        if not employee_name:
            frappe.throw(_("Employee not found for the current user."))

        # Create a new ToDo record
        todo_record = frappe.new_doc("ToDo")
        todo_record.update({
            "status": "Open",
            "allocated_to": frappe.session.user,
            "description": f"Assignment for Project {project_name}",
            "reference_type": "Project",
            "reference_name": project_name,
            "assigned_by": frappe.session.user,
            "assigned_by_full_name": employee_name
        })
        todo_record.insert()

        return _("Project assignment created successfully.")

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), _("Project Assignment Error"))
        frappe.throw(_("An error occurred while assigning the project. Please check the error logs."))

