import frappe

@frappe.whitelist()
def fetch_projects():
    # Fetch project data from Project doctype
    projects = frappe.get_all("Project", fields=["name as Name", "status as Status","notes as Notes","project_name as Project","customer as Customer"])  # Adjust fields as per your project doctype
    
    # Return project data
    return projects
