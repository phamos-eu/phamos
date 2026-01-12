import frappe

def execute():
    timesheets = frappe.get_all("Timesheet", fields=["name", "parent_project"])

    for t in timesheets:
        if not t.parent_project:
            continue

        project_name = frappe.db.get_value("Project", t.parent_project, "project_name")

        if project_name:
            frappe.db.set_value("Timesheet", t.name, "project_name", project_name)

    frappe.db.commit()
