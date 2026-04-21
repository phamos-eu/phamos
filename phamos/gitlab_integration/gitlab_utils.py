from frappe.auth import get_decrypted_password
import requests
import frappe
from frappe.utils import now_datetime

def get_gitlab_headers():
    settings = frappe.get_single("GitLab Settings")
    return {
        "PRIVATE-TOKEN": get_decrypted_password("GitLab Settings", "GitLab Settings", "access_token")
    }


# Cache so we don't call /api/v4/users/{id} more than once per user per sync run
_user_email_cache = {}

def get_user_email(user_id):
    """
    Try to resolve a GitLab user's email from their user ID.
    Falls back to None silently if the token doesn't have permission.
    Results are cached for the lifetime of the current process/sync run.
    """
    if not user_id:
        return None

    if user_id in _user_email_cache:
        return _user_email_cache[user_id]

    try:
        settings = frappe.get_single("GitLab Settings")
        url = f"{settings.gitlab_url}/api/v4/users/{user_id}"
        response = requests.get(url, headers=get_gitlab_headers(), timeout=10)

        if response.status_code == 200:
            data = response.json()
            # GitLab returns public_email if set, otherwise email (admin only)
            email = data.get("public_email") or data.get("email") or None
            _user_email_cache[user_id] = email
            return email
    except Exception:
        pass

    _user_email_cache[user_id] = None
    return None

def get_all_projects():
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url}/api/v4/projects?membership=true"
    
    response = requests.request("GET", url, headers=get_gitlab_headers())

    response.raise_for_status()
    return response.json()

def get_all_groups():
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url}/api/v4/groups?all_available=true"
    
    response = requests.request("GET", url, headers=get_gitlab_headers())

    response.raise_for_status()
    return response.json()

@frappe.whitelist()
def sync_gitlab_labels():
    settings = frappe.get_single("GitLab Settings")

    if not settings.gitlab_url:
        frappe.throw("GitLab URL not set")

    headers = get_gitlab_headers()

    projects = frappe.get_all(
        "GitLab Project",
        fields=["name", "project_id"]
    )

    total_synced = 0

    for project in projects:
        try:
            page = 1

            while True:
                url = f"{settings.gitlab_url}/api/v4/projects/{project.project_id}/labels?page={page}&per_page=100"

                resp = requests.get(url, headers=headers)

                if resp.status_code != 200:
                    frappe.log_error(resp.text, "GitLab Label Sync Error")
                    break

                labels = resp.json()

                if not labels:
                    break

                for label in labels:
                    label_id = label.get("id")

                    # Check if already exists
                    existing = frappe.db.get_value(
                        "GitLab Labels",
                        {
                            "label_id": label_id,
                            "project": project.name
                        },
                        "name"
                    )

                    data = {
                        "doctype": "GitLab Labels",
                        "label_id": label_id,
                        "name1": label.get("name"),
                        "text_color": label.get("text_color"),
                        "color": label.get("color"),
                        "priority": label.get("priority"),
                        "project": project.name
                    }

                    if existing:
                        doc = frappe.get_doc("GitLab Labels", existing)
                        doc.update(data)
                        doc.save(ignore_permissions=True)
                    else:
                        doc = frappe.get_doc(data)
                        doc.insert(ignore_permissions=True)

                    total_synced += 1

                page += 1

        except Exception as e:
            frappe.log_error(frappe.get_traceback(), "GitLab Label Sync Failed")

    frappe.db.commit()

    return f"{total_synced} labels synced successfully"

@frappe.whitelist()
def sync_groups_only():
    groups = get_all_groups()

    # Step 1: FEtch existing group_ids from DB
    existing_groups = frappe.get_all("GitLab Group", fields=["group_id"])
    existing_group_ids = {g.group_id for g in existing_groups}

    new_count = 0

    for group in groups:
        # Step 2: Only new groups process 
        if group["id"] in existing_group_ids:
            continue

        doc = frappe.new_doc("GitLab Group")
        doc.group_id = group["id"]
        doc.title = group["name"]
        doc.path = group["path"]
        doc.full_path = group["full_path"]
        doc.web_url = group["web_url"]

        doc.save(ignore_permissions=True)
        new_count += 1

    frappe.db.commit()

    return f"{new_count} new groups synced successfully"


def get_issues_for_project(project_id, updated_after=None):
    settings = frappe.get_single("GitLab Settings")
    base_url = f"{settings.gitlab_url}/api/v4/projects/{project_id}/issues"

    all_issues = []
    page = 1
    per_page = 100

    while True:
        params = {
            "state": "opened",
            "per_page": per_page,
            "page": page
        }

        if updated_after:
            params["updated_after"] = updated_after

        response = requests.get(base_url, headers=get_gitlab_headers(), params=params)
        response.raise_for_status()

        issues = response.json()
        if not issues:
            break

        all_issues.extend(issues)
        page += 1

    return all_issues


def get_issue_parent(project_path, issue_iid):
    """
    Fetch parent issue for a given issue using GraphQL
    """
    settings = frappe.get_single("GitLab Settings")
    graphql_url = f"{settings.gitlab_url}/api/graphql"
    
    query = """
    query GetWorkItemWithParent($projectPath: ID!, $iid: String!) {
      namespace(fullPath: $projectPath) {
        workItem(iid: $iid) {
          id
          widgets {
            __typename
            ... on WorkItemWidgetHierarchy {
              parent {
                id
                title
                iid
                webUrl
              }
            }
          }
        }
      }
    }
    """
    
    payload = {
        "query": query,
        "variables": {
            "projectPath": project_path,
            "iid": str(issue_iid)
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "PRIVATE-TOKEN": get_decrypted_password("GitLab Settings", "GitLab Settings", "access_token")
    }
    
    try:
        response = requests.post(graphql_url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        # Check for GraphQL errors
        if "errors" in data:
            frappe.log_error(
                title="GitLab GraphQL Error",
                message=f"Issue IID: {issue_iid}, Errors: {data['errors']}"
            )
            return None
        
        # Extract work item data
        work_item = data.get("data", {}).get("namespace", {}).get("workItem")
        if not work_item:
            return None
        
        # Find hierarchy widget and extract parent
        for widget in work_item.get("widgets", []):
            if widget.get("__typename") == "WorkItemWidgetHierarchy":
                parent = widget.get("parent")
                if parent:
                    return {
                        "title": parent.get("title"),
                        "iid": parent.get("iid"),
                        "web_url": parent.get("webUrl")
                    }
                break
        
        return None
        
    except Exception as e:
        frappe.log_error(
            title="GitLab Parent Fetch Error",
            message=f"Project: {project_path}, Issue IID: {issue_iid}, Error: {str(e)}"
        )
        return None


def get_milestones_for_project(project_id):
    settings = frappe.get_single("GitLab Settings")
    base_url = settings.gitlab_url.rstrip("/")

    headers = get_gitlab_headers()
    milestones = []
    page = 1

    while True:
        url = f"{base_url}/api/v4/projects/{project_id}/milestones"
        params = {"per_page": 100, "page": page}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            break

        data = response.json()
        if not data:
            break

        milestones.extend(data)
        page += 1

    return milestones


@frappe.whitelist()
def sync_projects_only():
    projects = get_all_projects()

    for project in projects:
        # 1. Create / Update GitLab Project
        existing = frappe.db.exists("GitLab Project", {"project_id": project["id"]})
        if existing:
            doc = frappe.get_doc("GitLab Project", existing)
        else:
            doc = frappe.new_doc("GitLab Project")
            doc.project_id = project["id"]

        doc.title = project["name"]
        doc.namespace = project.get("path_with_namespace")
        doc.web_url = project["web_url"]
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    return "Projects synced successfully"


@frappe.whitelist()
def sync_issues_only():
    """Sirf issues sync karo — update bhi karo agar fields change hui hain"""

    projects = frappe.get_all(
        "GitLab Project",
        fields=["name", "project_id", "last_synced", "title", "namespace"]
    )

    for project in projects:
        try:
            issues = get_issues_for_project(project["project_id"], project.get("last_synced"))
            project_path = project.get("namespace") or None

            issue_map = {}

            for issue in issues:
                try:
                    # 🔹 Milestone handling (FIX)
                    milestone_title = issue.get("milestone", {}).get("title") if issue.get("milestone") else None
                    milestone_name = None

                    if milestone_title:
                        milestone_name = frappe.db.get_value(
                            "GitLab Milestones",
                            {"title": milestone_title},
                            "name"
                        )

                        if not milestone_name:
                            milestone_doc = frappe.new_doc("GitLab Milestones")
                            milestone_doc.title = milestone_title
                            milestone_doc.save(ignore_permissions=True)
                            milestone_name = milestone_doc.name

                    existing_issue = frappe.db.exists(
                        "GitLab Issue",
                        {
                            "issue_id": issue["iid"],
                            "gitlab_project": project["name"]
                        }
                    )

                    # Resolve assignee fields once for this issue
                    assignee_data = issue.get("assignee") or {}
                    assignee_name = assignee_data.get("name", "")
                    assignee_username = assignee_data.get("username", "")
                    assignee_id = assignee_data.get("id")
                    assignee_email = get_user_email(assignee_id) if assignee_id else ""

                    if existing_issue:
                        # ✅ Existing issue — update all fields including new ones
                        gitlab_issue_doc = frappe.get_doc("GitLab Issue", existing_issue)
                        issue_map[str(issue["iid"])] = existing_issue

                        gitlab_issue_doc.update({
                            "title": issue["title"],
                            "description": issue.get("description", ""),
                            "state": issue["state"],
                            "due_date": issue.get("due_date") or None,
                            "assignee": assignee_name,
                            "assignee_email": assignee_email or "",
                            "gitlab_username": assignee_username,
                            "issue_url": issue["web_url"],
                            "gitlab_milestone": milestone_name or gitlab_issue_doc.get("gitlab_milestone"),
                            "labels": ", ".join(issue.get("labels", [])),
                        })

                        gitlab_issue_doc.save(ignore_permissions=True)

                    else:
                        # ✅ New issue — populate all fields
                        gitlab_issue_doc = frappe.new_doc("GitLab Issue")

                        gitlab_issue_doc.update({
                            "issue_id": issue["iid"],
                            "title": issue["title"],
                            "description": issue.get("description", ""),
                            "state": issue["state"],
                            "due_date": issue.get("due_date") or None,
                            "assignee": assignee_name,
                            "assignee_email": assignee_email or "",
                            "gitlab_username": assignee_username,
                            "issue_url": issue["web_url"],
                            "gitlab_project": project["name"],
                            "gitlab_milestone": milestone_name,
                            "labels": ", ".join(issue.get("labels", [])),
                        })

                        gitlab_issue_doc.save(ignore_permissions=True)
                        issue_map[str(issue["iid"])] = gitlab_issue_doc.name

                except Exception as ex:
                    frappe.log_error(
                        title="GitLab Issue Sync Error",
                        message=(
                            f"Project: {project.get('title')}, "
                            f"Issue IID: {issue.get('iid')}, "
                            f"Error: {str(ex)}"
                        )
                    )

            # 🔁 Second pass: parent linking
            for issue in issues:
                try:
                    issue_doc_name = issue_map.get(str(issue["iid"]))
                    if not issue_doc_name:
                        continue

                    if project_path:
                        parent_info = get_issue_parent(project_path, issue["iid"])

                        if parent_info and parent_info.get("iid"):
                            parent_iid = str(parent_info["iid"])
                            parent_doc_name = issue_map.get(parent_iid)

                            if parent_doc_name:
                                gitlab_issue_doc = frappe.get_doc("GitLab Issue", issue_doc_name)
                                gitlab_issue_doc.parent_issue = parent_doc_name
                                gitlab_issue_doc.save(ignore_permissions=True)

                except Exception as ex:
                    frappe.log_error(
                        title="GitLab Parent Link Error",
                        message=(
                            f"Project: {project.get('title')}, "
                            f"Issue IID: {issue.get('iid')}, "
                            f"Error: {str(ex)}"
                        )
                    )

            # ✅ Update last_synced
            project_doc = frappe.get_doc("GitLab Project", project["name"])
            project_doc.last_synced = now_datetime()
            project_doc.save(ignore_permissions=True)

        except Exception as ex:
            frappe.log_error(
                title="GitLab Project Sync Error",
                message=f"Project: {project.get('title')}, Error: {str(ex)}"
            )

    frappe.db.commit()
    return "Issues synced successfully"


@frappe.whitelist()
def sync_gitlab_milestones():
    projects = get_all_projects()

    for project in projects:
        existing_project = frappe.db.exists(
            "GitLab Project",
            {"project_id": project["id"]}
        )
        if not existing_project:
            continue

        milestones = get_milestones_for_project(project["id"])

        for milestone in milestones:
            try:
                existing_milestone = frappe.db.get_value(
                    "GitLab Milestones",
                    {
                        "milestone_id": int(milestone["id"]),
                        "gitlab_project": existing_project
                    },
                    "name"
                )

                if existing_milestone:
                    doc = frappe.get_doc("GitLab Milestones", existing_milestone)
                else:
                    doc = frappe.new_doc("GitLab Milestones")
                    doc.milestone_id   = int(milestone["id"])
                    doc.gitlab_project = existing_project
                    # Use project+milestone_id as name to avoid title collisions across projects
                    doc.name = f"{existing_project}-{milestone['id']}"

                doc.milestone_iid  = int(milestone["iid"])
                doc.title          = milestone["title"]
                doc.description    = milestone.get("description") or ""
                doc.state          = milestone["state"]
                doc.start_date     = milestone.get("start_date") or None
                doc.due_date       = milestone.get("due_date") or None
                doc.expired        = 1 if milestone.get("expired") else 0
                doc.web_url        = milestone.get("web_url") or ""
                doc.save(ignore_permissions=True)

            except Exception as ex:
                # Roll back the failed statement so the transaction stays usable
                frappe.db.rollback()
                frappe.log_error(
                    title="GitLab Milestone Sync Error",
                    message=(
                        f"Project: {project.get('name')}, "
                        f"Milestone ID: {milestone.get('id')}, "
                        f"Error: {str(ex)}"
                    )
                )

    frappe.db.commit()
    return "Milestones synced successfully"

@frappe.whitelist()
def sync_gitlab_data():
    """
    Full sync in order: projects → milestones → issues.
    This is what the Dev Action Panel sync button calls.
    """
    sync_projects_only()
    sync_gitlab_milestones()
    sync_issues_only()
    return "Sync complete"


@frappe.whitelist()
def sync_gitlab_data_background():
    frappe.enqueue(
        method="phamos.gitlab_integration.gitlab_utils.sync_gitlab_data",
        queue="long",
        timeout=60 * 60,
        is_async=True
    )
    return {
        "status": "queued",
        "message": "GitLab sync queued as background job",
    }
