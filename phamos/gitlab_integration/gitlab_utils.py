from frappe.auth import get_decrypted_password
import requests
import frappe
from frappe.utils import now_datetime

def get_gitlab_headers():
    settings = frappe.get_single("GitLab Settings")
    return {
        "PRIVATE-TOKEN": get_decrypted_password("GitLab Settings", "GitLab Settings", "access_token")
    }

def get_all_projects():
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url}/api/v4/projects?membership=true"
    
    response = requests.request("GET", url, headers=get_gitlab_headers())

    response.raise_for_status()
    return response.json()

def get_issues_for_project(project_id):
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url}/api/v4/projects/{project_id}/issues?per_page=100"
    response = requests.get(url, headers=get_gitlab_headers())

    response.raise_for_status()
    return response.json()

@frappe.whitelist()
def sync_gitlab_data():
    projects = get_all_projects()
    
    for project in projects:
        existing = frappe.db.exists("GitLab Project", {"project_id": project["id"]})
        if existing:
            doc = frappe.get_doc("GitLab Project", existing)
            # doc.issues = []
        else:
            doc = frappe.new_doc("GitLab Project")
            doc.project_id = project["id"]

        doc.title = project["name"]
        doc.namespace = project["name_with_namespace"]
        doc.web_url = project["web_url"]
        doc.last_synced = now_datetime()
        doc.save(ignore_permissions=True)
        issues = get_issues_for_project(project["id"])
        for issue in issues:
            try:
                gitlab_issue_doc = frappe.new_doc("GitLab Issue")
                gitlab_issue_doc.update({
                    "issue_id": issue["iid"],
                    "title": issue["title"],
                    "description": issue.get("description", ""),
                    "state": issue["state"],
                    "assignee": issue["assignee"]["name"] if issue.get("assignee") else "",
                    # "created_at": issue["created_at"],
                    # "updated_at": issue["updated_at"],
                    "issue_url": issue["web_url"],
                    "gitlab_project": doc.name
                })
                gitlab_issue_doc.save(ignore_permissions=True)
            except Exception as ex:
                print(ex)

        
    frappe.db.commit()
