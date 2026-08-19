from frappe.auth import get_decrypted_password
import requests
import frappe
from frappe.utils import now_datetime
import json
import hashlib
import hmac
import time
from datetime import datetime


def _set_gitlab_issue_value_with_retry(name, data, max_retries=3):
    """frappe.db.set_value with retry-on-lock-timeout.

    Concurrent GitLab webhooks landing for the same issue can hit MySQL's
    lock wait timeout (1205) while another request holds the row lock.
    Retrying the same write after a short backoff resolves the transient
    contention without changing what gets written or when.
    """
    for attempt in range(max_retries + 1):
        try:
            frappe.db.set_value("GitLab Issue", name, data, update_modified=True)
            return
        except (frappe.QueryTimeoutError, frappe.QueryDeadlockError):
            if attempt < max_retries:
                frappe.db.rollback()
                time.sleep(1 + attempt)
                continue
            raise


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

def get_all_projects(page=1, per_page=100):
    settings = frappe.get_single("GitLab Settings")
    
    all_projects = []
    current_page = page

    while True:
        url = f"{settings.gitlab_url}/api/v4/projects?page={current_page}&per_page={per_page}&order_by=id&sort=asc"
        
        response = requests.request("GET", url, headers=get_gitlab_headers())
        response.raise_for_status()
        data = response.json()
        if not data:
            break
            
        all_projects.extend(data)
        
        total_pages = int(response.headers.get("X-Total-Pages", 1))
        if current_page >= total_pages:
            break
        current_page += 1

    return all_projects

def get_all_groups(page=1, per_page=100):
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url}/api/v4/groups?all_available=true&page={page}&per_page={per_page}"
    
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
                    label_name = label.get("name")

                    # Check by label name instead of ID
                    existing = frappe.db.get_value(
                        "GitLab Labels",
                        {
                            "name1": label_name,
                        },
                        "name"
                    )

                    data = {
                        "doctype": "GitLab Labels",
                        "label_id": label.get("id"),
                        "name1": label_name,
                        "text_color": label.get("text_color"),
                        "color": label.get("color"),
                        "priority": label.get("priority"),
                    }

                    if existing:
                        doc = frappe.get_doc("GitLab Labels", existing)

                        # Optional:
                        # only update empty fields
                        doc.label_id = doc.label_id or data["label_id"]
                        doc.text_color = doc.text_color or data["text_color"]
                        doc.color = doc.color or data["color"]
                        doc.priority = doc.priority or data["priority"]

                        doc.save(ignore_permissions=True)

                    else:
                        doc = frappe.get_doc(data)
                        doc.insert(ignore_permissions=True)

                    total_synced += 1

                page += 1

        except Exception:
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


def get_issues_for_project(project_id, updated_after=None, state="all"):
    settings = frappe.get_single("GitLab Settings")
    base_url = f"{settings.gitlab_url}/api/v4/projects/{project_id}/issues"

    all_issues = []
    page = 1
    per_page = 100

    while True:
        params = {
            "state": state,
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


def get_issue_for_project(project_id, issue_iid):
    settings = frappe.get_single("GitLab Settings")
    base_url = settings.gitlab_url.rstrip("/")
    response = requests.get(
        f"{base_url}/api/v4/projects/{project_id}/issues/{issue_iid}",
        headers=get_gitlab_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_issue_timestamp_fields(issue):
    return {
        "created_at": _parse_gitlab_datetime(issue.get("created_at")),
        "closed_at": _parse_gitlab_datetime(issue.get("closed_at")),
    }


def _normalize_issue_text(value):
    """Keep text storage format stable so form editors don't mark docs dirty on load."""
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n")


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
        namespace = project.get("namespace", {})
        if namespace.get("kind") == "group":
            group_name = frappe.db.get_value("GitLab Group", {"group_id": namespace["id"]}, "name")
            doc.group = group_name or None
        else:
            doc.group = None
        doc.save(ignore_permissions=True)

    frappe.db.commit()
    return "Projects synced successfully"

@frappe.whitelist()
def sync_all_issues():
    projects = frappe.get_all(
        "GitLab Project",
        fields=["name", "project_id", "last_synced", "title", "namespace"]
    )

    for project in projects:
        try:
            # ── Full fetch (no last_synced)
            issues = get_issues_for_project(project["project_id"])
            project_path = project.get("namespace") or None
            issue_map = {}

            # ── Step 1: Fetched issues iids (include assigned + unassigned issues)
            fetched_iids = {str(issue["iid"]) for issue in issues}


            # ── Step 3: Upsert all fetched (opened) issues ──
            for issue in issues:
                try:
                    milestone_id = (
                        issue.get("milestone", {}).get("id")
                        if issue.get("milestone") else None
                    )
                    milestone_name = None
                    if milestone_id and project["name"]:
                        milestone_name = frappe.db.get_value(
                            "GitLab Milestones",
                            {"milestone_id": milestone_id, "gitlab_project": project["name"]},
                            "name"
                        )
                        if not milestone_name:
                            milestone_doc = frappe.new_doc("GitLab Milestones")
                            milestone_doc.milestone_id = milestone_id
                            milestone_doc.gitlab_project = project["name"]
                            milestone_doc.save(ignore_permissions=True)
                            milestone_name = milestone_doc.name

                    existing_issue = frappe.db.exists(
                        "GitLab Issue",
                        {"issue_id": str(issue["iid"]), "gitlab_project": project["name"]}
                    )

                    assignee_data = issue.get("assignee") or {}
                    assignee_name = assignee_data.get("name", "")
                    assignee_username = assignee_data.get("username", "")
                    assignee_id = assignee_data.get("id")
                    assignee_email = get_user_email(assignee_id) if assignee_id else ""

                    fields = {
                        "title": _normalize_issue_text(issue.get("title", "")),
                        "description": _normalize_issue_text(issue.get("description", "")),
                        "state": issue["state"],
                        "due_date": issue.get("due_date") or None,
                        "assignee": assignee_name,
                        "assignee_email": assignee_email or "",
                        "gitlab_username": assignee_username,
                        "issue_url": issue["web_url"],
                        "labels": ", ".join(issue.get("labels", [])),
                    }
                    fields.update(_get_issue_timestamp_fields(issue))
                    if milestone_name:
                        fields["gitlab_milestone"] = milestone_name

                    if existing_issue:
                        gitlab_issue_doc = frappe.get_doc("GitLab Issue", existing_issue)
                        gitlab_issue_doc.update(fields)
                        gitlab_issue_doc.save(ignore_permissions=True)
                        issue_map[str(issue["iid"])] = existing_issue
                    else:
                        gitlab_issue_doc = frappe.new_doc("GitLab Issue")
                        gitlab_issue_doc.update(fields)
                        gitlab_issue_doc.update({
                            "issue_id": str(issue["iid"]),
                            "gitlab_project": project["name"],
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

            # ── Step 4: Parent linking ──
            for issue in issues:
                try:
                    issue_doc_name = issue_map.get(str(issue["iid"]))
                    if not issue_doc_name or not project_path:
                        continue

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

            # ── Step 5: Update last_synced ──
            project_doc = frappe.get_doc("GitLab Project", project["name"])
            project_doc.last_synced = now_datetime()
            project_doc.save(ignore_permissions=True)
            frappe.db.commit()

        except Exception as ex:
            frappe.db.rollback()
            frappe.log_error(
                title="GitLab Project Sync Error",
                message=f"Project: {project.get('title')}, Error: {str(ex)}"
            )

    return "Issues synced successfully"

@frappe.whitelist()
def sync_issues_for_project(project_name):
    project = frappe.get_value(
        "GitLab Project",
        project_name,
        ["name", "project_id", "title", "namespace"],
        as_dict=True
    )

    if not project:
        frappe.throw("Project not found")

    try:
        issues = get_issues_for_project(project.project_id)
        project_path = project.namespace or None
        issue_map = {}

        # Include assigned + unassigned issues to keep all GitLab issues in sync.
        fetched_iids = {str(issue["iid"]) for issue in issues}


        # Create / Update issues
        for issue in issues:
            try:
                milestone_id = (
                    issue.get("milestone", {}).get("id")
                    if issue.get("milestone") else None
                )

                milestone_name = None

                if milestone_id:
                    milestone_name = frappe.db.get_value(
                        "GitLab Milestones",
                        {
                            "milestone_id": milestone_id,
                            "gitlab_project": project.name
                        },
                        "name"
                    )

                existing_issue = frappe.db.exists(
                    "GitLab Issue",
                    {
                        "issue_id": str(issue["iid"]),
                        "gitlab_project": project.name
                    }
                )

                assignee_data = issue.get("assignee") or {}
                assignee_id = assignee_data.get("id")

                fields = {
                    "title": _normalize_issue_text(issue.get("title", "")),
                    "description": _normalize_issue_text(issue.get("description", "")),
                    "state": issue["state"],
                    "due_date": issue.get("due_date") or None,
                    "assignee": assignee_data.get("name", ""),
                    "assignee_email": get_user_email(assignee_id) if assignee_id else "",
                    "gitlab_username": assignee_data.get("username", ""),
                    "issue_url": issue["web_url"],
                    "labels": ", ".join(issue.get("labels", [])),
                }
                fields.update(_get_issue_timestamp_fields(issue))

                if milestone_name:
                    fields["gitlab_milestone"] = milestone_name

                if existing_issue:
                    doc = frappe.get_doc("GitLab Issue", existing_issue)
                    doc.update(fields)
                    doc.save(ignore_permissions=True)
                    issue_map[str(issue["iid"])] = doc.name
                else:
                    doc = frappe.new_doc("GitLab Issue")
                    doc.update(fields)
                    doc.issue_id = str(issue["iid"])
                    doc.gitlab_project = project.name
                    doc.save(ignore_permissions=True)
                    issue_map[str(issue["iid"])] = doc.name

            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"GitLab Issue Sync Error - {project.title}"
                )

        # Parent linking
        for issue in issues:
            try:
                issue_doc_name = issue_map.get(str(issue["iid"]))

                if not issue_doc_name or not project_path:
                    continue

                parent_info = get_issue_parent(project_path, issue["iid"])

                if parent_info and parent_info.get("iid"):
                    parent_doc_name = issue_map.get(str(parent_info["iid"]))

                    if parent_doc_name:
                        doc = frappe.get_doc("GitLab Issue", issue_doc_name)
                        doc.parent_issue = parent_doc_name
                        doc.save(ignore_permissions=True)

            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"GitLab Parent Link Error - {project.title}"
                )

        frappe.db.set_value(
            "GitLab Project",
            project.name,
            "last_synced",
            now_datetime()
        )

        frappe.db.commit()

        return f"Issues synced successfully for {project.title}"

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            frappe.get_traceback(),
            f"GitLab Project Sync Error - {project.title}"
        )
        frappe.throw("Failed to sync issues")

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
def register_webhooks_for_all_projects():
    settings = frappe.get_single("GitLab Settings")
    
    if not settings.gitlab_url:
        frappe.throw("GitLab URL not set")

    # Webhook secret get 
    try:
        webhook_secret = get_decrypted_password(
            "GitLab Settings", "GitLab Settings", "webhook_secret"
        )
    except Exception:
        webhook_secret = None

    # Webhook receiver URL — ngrok/server URL 
    webhook_url = f"{settings.webhook_base_url}/api/method/phamos.gitlab_integration.gitlab_utils.gitlab_webhook_receiver"

    headers = get_gitlab_headers()
    projects = frappe.get_all(
        "GitLab Project",
        fields=["name", "project_id", "title"]
    )

    results = []

    for project in projects:
        try:
            project_id = project["project_id"]

            # ── Step 1: Existing webhooks check (duplicate avoid) ──
            existing_url = f"{settings.gitlab_url}/api/v4/projects/{project_id}/hooks"
            existing_resp = requests.get(existing_url, headers=headers)
            existing_hooks = existing_resp.json() if existing_resp.status_code == 200 else []

            existing_hook = next(
                (hook for hook in existing_hooks if hook.get("url") == webhook_url),
                None,
            )

            if existing_hook:
                if existing_hook.get("note_events"):
                    results.append(f"⏭ {project['title']} — already registered")
                    continue
                # Hook exists from before Note Hook support was added — enable it.
                update_resp = requests.put(
                    f"{existing_url}/{existing_hook['id']}",
                    json={"note_events": True, "enable_ssl_verification": False},
                    headers=headers,
                )
                if update_resp.status_code == 200:
                    results.append(f"🔄 {project['title']} — enabled note_events on existing webhook")
                else:
                    results.append(f"❌ {project['title']} — failed to enable note_events: {update_resp.text}")
                continue

            # ── Step 2: Webhook register ──
            payload = {
                "url": webhook_url,
                "issues_events": True,
                "note_events": True,
                "enable_ssl_verification": False,
            }

            if webhook_secret:
                payload["token"] = webhook_secret

            resp = requests.post(existing_url, json=payload, headers=headers)

            if resp.status_code == 201:
                results.append(f"✅ {project['title']} — webhook registered")
            else:
                results.append(f"❌ {project['title']} — failed: {resp.text}")

        except Exception as ex:
            results.append(f"❌ {project['title']} — error: {str(ex)}")

    return "\n".join(results)

@frappe.whitelist()
def sync_gitlab_data():
    """
    Full sync in order: projects → milestones → issues.
    This is what the Dev Action Panel sync button calls.
    """
    sync_projects_only()
    sync_gitlab_milestones()
    sync_all_issues()
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



@frappe.whitelist(allow_guest=True)
def gitlab_webhook_receiver():
    settings = frappe.get_single("GitLab Settings")
    
    try:
        expected_secret = get_decrypted_password(
            "GitLab Settings", "GitLab Settings", "webhook_secret"
        )
    except Exception:
        expected_secret = None

    if expected_secret:
        incoming_token = frappe.request.headers.get("X-Gitlab-Token", "")
        if incoming_token != expected_secret:
            frappe.response.http_status_code = 401
            return {"error": "Unauthorized"}

    try:
        payload = json.loads(frappe.request.data)
    except Exception:
        frappe.response.http_status_code = 400
        return {"error": "Invalid JSON"}

    event_type = frappe.request.headers.get("X-Gitlab-Event", "")

    if event_type not in ("Issue Hook", "Note Hook"):
        return {"status": "ignored", "event": event_type}

    try:
        if event_type == "Issue Hook":
            _handle_issue_webhook(payload)
        else:
            _handle_note_webhook(payload)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "GitLab Webhook Error")
        frappe.response.http_status_code = 500
        return {"error": "Internal error"}

    return {"status": "ok"}


def _handle_issue_webhook(payload):
   
    action        = payload.get("object_attributes", {}).get("action")
    issue_attrs   = payload.get("object_attributes", {})
    project_info  = payload.get("project", {})
    gl_project_id = project_info.get("id")

    project_doc_name = frappe.db.get_value(
        "GitLab Project",
        {"project_id": gl_project_id},
        "name"
    )

    if not project_doc_name:
        frappe.log_error(
            title="GitLab Webhook - Unknown Project",
            message=f"Project ID {gl_project_id} not found in GitLab Project doctype."
        )
        return

    project_doc = frappe.get_doc("GitLab Project", project_doc_name)

    # Always cast iid to string to avoid type mismatch with DB
    issue_iid = str(issue_attrs.get("iid"))

    if action == "delete":
        existing = frappe.db.get_value(
            "GitLab Issue",
            {"issue_id": issue_iid, "gitlab_project": project_doc_name},
            "name"
        )
        if existing:
            frappe.delete_doc("GitLab Issue", existing, ignore_permissions=True)
            frappe.db.commit()
        return

    # ── CREATE / UPDATE / CLOSE / REOPEN ─────────────────────────────────
    milestone_name = _resolve_milestone_from_webhook(issue_attrs, project_doc_name)

    assignee_name     = ""
    assignee_username = ""
    assignee_email    = ""

    assignees = payload.get("assignees", [])
    if assignees:
        first = assignees[0]
        assignee_name     = first.get("name", "")
        assignee_username = first.get("username", "")
        assignee_id       = first.get("id")
        assignee_email    = get_user_email(assignee_id) or ""

    labels_list = [lbl.get("title", "") for lbl in payload.get("labels", [])]
    labels_str  = ", ".join(filter(None, labels_list))

    state = issue_attrs.get("state", "opened")
    timestamp_data = _get_issue_timestamp_fields(issue_attrs)
    if state == "closed" and not timestamp_data.get("closed_at"):
        try:
            issue_detail = get_issue_for_project(gl_project_id, issue_iid)
            timestamp_data.update(_get_issue_timestamp_fields(issue_detail))
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"GitLab Issue Timestamp Fetch Failed - {project_doc.title}"
            )

    data = {
        "title"          : _normalize_issue_text(issue_attrs.get("title", "")),
        "description"    : _normalize_issue_text(issue_attrs.get("description", "")),
        "state"          : state,
        "due_date"       : issue_attrs.get("due_date") or None,
        "assignee"       : assignee_name,
        "assignee_email" : assignee_email,
        "gitlab_username": assignee_username,
        "issue_url"      : issue_attrs.get("url", ""),
        "labels"         : labels_str,
        "gitlab_milestone": milestone_name,
    }
    data.update(timestamp_data)

    existing = frappe.db.get_value(
        "GitLab Issue",
        {"issue_id": issue_iid, "gitlab_project": project_doc_name},
        "name"
    )

    if existing:
        # Detect newly added prod labels before overwriting the labels field
        _stamp_prod_labels_on_change(existing, labels_list)
        # use set_value to avoid TimestampMismatchError on concurrent webhooks
        _set_gitlab_issue_value_with_retry(existing, data)
    else:
        try:
            doc = frappe.new_doc("GitLab Issue")
            doc.update(data)
            doc.issue_id       = issue_iid
            doc.gitlab_project = project_doc_name
            # Stamp prod label timestamps for a brand-new issue
            _stamp_prod_labels_initial(doc, labels_list)
            doc.insert(ignore_permissions=True)
            _try_link_parent_from_webhook(
                doc.name,
                project_doc.namespace,
                issue_iid
            )
        except frappe.DuplicateEntryError:
            frappe.db.rollback()
            existing = frappe.db.get_value(
                "GitLab Issue",
                {"issue_id": issue_iid, "gitlab_project": project_doc_name},
                "name"
            )
            if existing:
                _stamp_prod_labels_on_change(existing, labels_list)
                _set_gitlab_issue_value_with_retry(existing, data)

    frappe.db.commit()


_PROD_LABEL_FIELDS = {
    "Merged into Production": "merged_to_production_at",
    "Testing on Production": "testing_on_production_at",
}


def _stamp_prod_labels_on_change(issue_doc_name, new_labels_list):
    """Set timestamp fields when a prod label is newly added (not already stored)."""
    ts_fields = frappe.db.get_value(
        "GitLab Issue",
        issue_doc_name,
        ["labels", "merged_to_production_at", "testing_on_production_at"],
        as_dict=True,
    ) or {}
    old_labels = {l.strip() for l in (ts_fields.get("labels") or "").split(",") if l.strip()}
    new_labels = set(new_labels_list)
    now = now_datetime()

    updates = {}
    for label, field in _PROD_LABEL_FIELDS.items():
        if label in new_labels and label not in old_labels and not ts_fields.get(field):
            updates[field] = now

    if updates:
        frappe.db.set_value("GitLab Issue", issue_doc_name, updates, update_modified=False)


def _stamp_prod_labels_initial(doc, labels_list):
    """Set timestamp fields on a brand-new issue that already carries a prod label."""
    now = now_datetime()
    for label, field in _PROD_LABEL_FIELDS.items():
        if label in labels_list:
            setattr(doc, field, now)


def _resolve_milestone_from_webhook(issue_attrs, project_doc_name):
   
    milestone_id = issue_attrs.get("milestone_id")
    if not milestone_id:
        return None

    milestone_name = frappe.db.get_value(
        "GitLab Milestones",
        {"milestone_id": int(milestone_id), "gitlab_project": project_doc_name},
        "name"
    )
    return milestone_name or None


def _try_link_parent_from_webhook(issue_doc_name, project_path, issue_iid):
   
    if not project_path:
        return
    try:
        parent_info = get_issue_parent(project_path, issue_iid)
        if parent_info and parent_info.get("iid"):
            parent_doc_name = frappe.db.get_value(
                "GitLab Issue",
                {"issue_id": str(parent_info["iid"])},
                "name"
            )
            if parent_doc_name:
                # ── FIX: set_value instead of get_doc + save ──
                frappe.db.set_value(
                    "GitLab Issue",
                    issue_doc_name,
                    "parent_issue",
                    parent_doc_name
                )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Webhook Parent Link Error")


def _parse_gitlab_datetime(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _upsert_issue_comment(issue_doc_name, note_id, author, body, commented_at):
    """Create or update a single 'GitLab Issue Comment' row on a GitLab Issue."""
    existing_row = frappe.db.exists(
        "GitLab Issue Comment", {"note_id": note_id, "parent": issue_doc_name}
    )
    if existing_row:
        frappe.db.set_value(
            "GitLab Issue Comment",
            existing_row,
            {"author": author, "comment": body, "commented_at": commented_at},
        )
        return

    issue_doc = frappe.get_doc("GitLab Issue", issue_doc_name)
    issue_doc.append("comments", {
        "note_id": note_id,
        "author": author,
        "comment": body,
        "commented_at": commented_at,
    })
    issue_doc.save(ignore_permissions=True)


def _handle_note_webhook(payload):
    obj_attrs = payload.get("object_attributes", {})

    # Only care about comments on Issues, and skip system-generated notes
    # (e.g. "changed label to X", "closed") — those aren't real discussion.
    if obj_attrs.get("noteable_type") != "Issue" or obj_attrs.get("system"):
        return

    project_info = payload.get("project", {})
    gl_project_id = project_info.get("id")
    project_doc_name = frappe.db.get_value(
        "GitLab Project", {"project_id": gl_project_id}, "name"
    )
    if not project_doc_name:
        return

    issue_info = payload.get("issue", {})
    issue_iid = str(issue_info.get("iid"))
    issue_doc_name = frappe.db.get_value(
        "GitLab Issue",
        {"issue_id": issue_iid, "gitlab_project": project_doc_name},
        "name",
    )
    if not issue_doc_name:
        return

    note_id = str(obj_attrs.get("id"))
    author = (payload.get("user") or {}).get("name", "")
    body = obj_attrs.get("note", "")
    commented_at = _parse_gitlab_datetime(obj_attrs.get("created_at")) or now_datetime()

    _upsert_issue_comment(issue_doc_name, note_id, author, body, commented_at)
    frappe.db.commit()


@frappe.whitelist()
def backfill_issue_comments(project_name=None):
    """
    One-off historical sync of non-system Issue comments via the GitLab API.
    Only needed for issues that existed before the Note Hook webhook was registered —
    new comments arrive live via _handle_note_webhook.
    """
    settings = frappe.get_single("GitLab Settings")
    base_url = settings.gitlab_url.rstrip("/")
    headers = get_gitlab_headers()

    filters = {"name": project_name} if project_name else {}
    projects = frappe.get_all("GitLab Project", filters=filters, fields=["name", "project_id"])

    synced = 0
    for project in projects:
        issues = frappe.get_all(
            "GitLab Issue",
            filters={"gitlab_project": project.name},
            fields=["name", "issue_id"],
        )
        for issue in issues:
            page = 1
            while True:
                resp = requests.get(
                    f"{base_url}/api/v4/projects/{project.project_id}/issues/{issue.issue_id}/notes",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                    timeout=30,
                )
                if resp.status_code != 200:
                    break
                notes = resp.json()
                if not notes:
                    break

                for note in notes:
                    if note.get("system"):
                        continue
                    _upsert_issue_comment(
                        issue.name,
                        str(note["id"]),
                        (note.get("author") or {}).get("name", ""),
                        note.get("body", ""),
                        _parse_gitlab_datetime(note.get("created_at")),
                    )
                    synced += 1

                page += 1

            # Commit after each issue rather than only at the very end, so a
            # timeout/kill on a large backfill only loses the current issue's
            # progress instead of the whole run.
            frappe.db.commit()

    return f"{synced} comments synced"


@frappe.whitelist()
def backfill_issue_timestamps(project_name=None, limit=None):
    """
    One-off sync of created_at/closed_at for GitLab Issues already stored in ERPNext.
    New and closed issues are kept updated by the normal issue sync/webhook flow.
    """
    if project_name:
        projects = frappe.get_all(
            "GitLab Project",
            filters={"name": project_name},
            fields=["name", "project_id"],
        )
        if not projects:
            projects = frappe.get_all(
                "GitLab Project",
                filters={"title": project_name},
                fields=["name", "project_id"],
            )
    else:
        projects = frappe.get_all("GitLab Project", fields=["name", "project_id"])

    limit = int(limit) if limit else None
    synced = 0
    for project in projects:
        issues = frappe.get_all(
            "GitLab Issue",
            filters={"gitlab_project": project.name},
            fields=["name", "issue_id"],
            limit_page_length=limit,
        )
        for issue in issues:
            try:
                issue_detail = get_issue_for_project(project.project_id, issue.issue_id)
                updates = _get_issue_timestamp_fields(issue_detail)
                if issue_detail.get("state"):
                    updates["state"] = issue_detail.get("state")

                frappe.db.set_value(
                    "GitLab Issue",
                    issue.name,
                    updates,
                    update_modified=False,
                )
                synced += 1
            except Exception:
                frappe.log_error(
                    frappe.get_traceback(),
                    f"GitLab Issue Timestamp Backfill Failed - {project.name} #{issue.issue_id}"
                )

        frappe.db.commit()

    return f"{synced} issue timestamps synced"


def _backfill_issue_comments_and_notify(project_name, notify_user):
    """Runs the backfill, then pushes a realtime summary to whoever triggered it —
    the background job's return value otherwise isn't visible anywhere in the UI."""
    result = backfill_issue_comments(project_name)
    frappe.publish_realtime(event="show_alert", message=f"✅ {result}", user=notify_user)


@frappe.whitelist()
def backfill_issue_comments_background(project_name=None):
    """UI-triggered async wrapper — backfilling all projects/issues can take
    long enough to exceed a web request's timeout, so run it on the long queue.
    Notifies the triggering user via a realtime alert once done, since the job's
    return value otherwise isn't visible anywhere."""
    frappe.enqueue(
        method="phamos.gitlab_integration.gitlab_utils._backfill_issue_comments_and_notify",
        queue="long",
        timeout=60 * 60,
        is_async=True,
        project_name=project_name,
        notify_user=frappe.session.user,
    )
    return {
        "status": "queued",
        "message": "Issue comment backfill queued as background job",
    }
