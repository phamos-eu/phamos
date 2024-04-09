import frappe

@frappe.whitelist()
def fetch_projects():
    # Custom SQL query to fetch project data
    projects = frappe.db.sql("""
        SELECT p.name AS name, p.status AS status, p.notes AS notes, p.project_name AS project_name,
               (SELECT customer_name FROM `tabCustomer` c WHERE p.customer = c.name) AS customer
        FROM `tabProject` p
    """, as_dict=True)

    # Return project data
    return projects

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
