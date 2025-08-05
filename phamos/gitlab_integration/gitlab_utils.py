from frappe.auth import get_decrypted_password
import requests
import frappe
from frappe.utils import now_datetime
import time

class GitLabSyncError(Exception):
    """Custom exception for GitLab sync errors"""
    pass

def get_gitlab_settings():
    """Get GitLab settings with validation"""
    settings = frappe.get_single("GitLab Settings")
    if not settings.gitlab_url or not settings.access_token:
        raise GitLabSyncError("GitLab URL or access token not configured")
    return settings

def make_gitlab_request(url, params=None, timeout=30):
    """Make GitLab API request with proper error handling"""
    headers = {
        "PRIVATE-TOKEN": get_decrypted_password("GitLab Settings", "GitLab Settings", "access_token"),
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise GitLabSyncError(f"GitLab API request timed out: {url}")
    except requests.exceptions.RequestException as e:
        raise GitLabSyncError(f"GitLab API request failed: {url} - {str(e)}")

def get_all_projects():
    """Fetch all GitLab projects with pagination"""
    settings = get_gitlab_settings()
    url = f"{settings.gitlab_url}/api/v4/projects"
    
    all_projects = []
    page = 1
    per_page = 100
    
    while True:
        params = {
            "membership": "true",
            "per_page": per_page,
            "page": page,
            "order_by": "updated_at",
            "sort": "desc"
        }
        
        try:
            projects = make_gitlab_request(url, params, timeout=30)
            if not projects:
                break
                
            all_projects.extend(projects)
            if len(projects) < per_page:
                break
                
            page += 1
            time.sleep(0.1)  # Rate limiting
            
        except GitLabSyncError as e:
            frappe.log_error(f"Error fetching projects page {page}: {str(e)}")
            break
    
    return all_projects

def get_project_issues(project_id, updated_after=None, max_issues=500):
    """Fetch issues for a specific project with incremental sync"""
    settings = get_gitlab_settings()
    url = f"{settings.gitlab_url}/api/v4/projects/{project_id}/issues"
    
    all_issues = []
    page = 1
    per_page = 50
    
    while len(all_issues) < max_issues:
        params = {
            "per_page": per_page,
            "page": page,
            "state": "opened",
            "order_by": "updated_at",
            "sort": "desc"
        }
        
        if updated_after:
            params["updated_after"] = updated_after.isoformat()
        
        try:
            issues = make_gitlab_request(url, params, timeout=15)
            if not issues:
                break
                
            all_issues.extend(issues)
            if len(issues) < per_page:
                break
                
            page += 1
            time.sleep(0.1)
            
        except GitLabSyncError as e:
            frappe.log_error(f"Error fetching issues for project {project_id}: {str(e)}")
            break
    
    return all_issues[:max_issues]

def sync_project(project_data, incremental=False):
    """Sync a single GitLab project with GitLab ID as name"""
    try:
        gitlab_id = str(project_data["id"])
        project_name = project_data.get('name', 'unknown')
        
        # Get or create project document using GitLab ID as name
        if frappe.db.exists("GitLab Project", gitlab_id):
            doc = frappe.get_doc("GitLab Project", gitlab_id)
            last_sync = doc.last_synced
        else:
            doc = frappe.new_doc("GitLab Project")
            doc.name = gitlab_id
            doc.project_id = project_data["id"]
            last_sync = None
        
        # Update project data
        doc.title = project_data["name"]
        doc.namespace = project_data["name_with_namespace"]
        doc.web_url = project_data["web_url"]
        doc.description = project_data.get("description", "")
        doc.visibility = project_data.get("visibility", "private")
        doc.last_synced = now_datetime()
        doc.save(ignore_permissions=True)
        
        # Sync issues
        updated_after = None
        if incremental and last_sync:
            updated_after = last_sync
        
        try:
            issues = get_project_issues(
                project_data["id"], 
                updated_after=updated_after,
                max_issues=200
            )
            
            sync_issues(doc.name, issues, incremental)
            
            return {
                "project": doc.name,
                "issues_synced": len(issues),
                "status": "success"
            }
            
        except Exception as issue_error:
            frappe.log_error(f"Error syncing issues for project {project_name}: {str(issue_error)}")
            return {
                "project": project_name,
                "issues_synced": 0,
                "status": "error",
                "error": f"Issue sync failed: {str(issue_error)}"
            }
        
    except Exception as e:
        error_msg = f"Error syncing project {project_data.get('name', 'unknown')}: {str(e)}"
        frappe.log_error(error_msg)
        return {
            "project": project_data.get('name', 'unknown'),
            "issues_synced": 0,
            "status": "error",
            "error": str(e)
        }

def sync_issues(project_name, issues, incremental=False):
    """Sync issues for a project with GitLab ID as name"""
    if not incremental:
        frappe.db.delete("GitLab Issue", {"gitlab_project": project_name})
    
    batch_size = 50
    for i in range(0, len(issues), batch_size):
        batch = issues[i:i + batch_size]
        
        for issue_data in batch:
            try:
                gitlab_issue_id = str(issue_data["id"])
                
                # Check if issue already exists using GitLab ID as name
                if frappe.db.exists("GitLab Issue", gitlab_issue_id):
                    doc = frappe.get_doc("GitLab Issue", gitlab_issue_id)
                else:
                    doc = frappe.new_doc("GitLab Issue")
                    doc.name = gitlab_issue_id
                    doc.issue_id = issue_data["iid"]
                    doc.gitlab_project = project_name
                
                # Update issue data
                doc.title = issue_data["title"]
                doc.description = issue_data.get("description", "")
                doc.state = issue_data["state"]
                doc.assignee = issue_data["assignee"]["name"] if issue_data.get("assignee") else ""
                doc.author = issue_data["author"]["name"] if issue_data.get("author") else ""
                doc.issue_url = issue_data["web_url"]
                doc.created_at = issue_data.get("created_at")
                doc.updated_at = issue_data.get("updated_at")
                doc.labels = ", ".join(issue_data.get("labels", []))
                doc.milestone = issue_data["milestone"]["title"] if issue_data.get("milestone") else ""
                
                doc.save(ignore_permissions=True)
                
            except Exception as e:
                frappe.log_error(f"Error saving issue {issue_data.get('id', 'unknown')}: {str(e)}")
        
        frappe.db.commit()
        time.sleep(0.05)

@frappe.whitelist()
def schedule_gitlab_sync(sync_type="full"):
    """Schedule GitLab sync as background job"""
    try:
        if sync_type == "full":
            job = frappe.enqueue(
                "phamos.gitlab_integration.gitlab_utils.perform_full_sync",
                queue="long",
                timeout=3600,
                job_name="GitLab Full Sync"
            )
        else:
            job = frappe.enqueue(
                "phamos.gitlab_integration.gitlab_utils.perform_incremental_sync",
                queue="long",
                timeout=1800,
                job_name="GitLab Incremental Sync"
            )
        
        frappe.msgprint(f"GitLab {sync_type} sync scheduled. Job ID: {job.id}", indicator="green")
        return {"status": "success", "job_id": job.id}
        
    except Exception as e:
        frappe.log_error(f"Error scheduling GitLab sync: {str(e)}")
        frappe.msgprint(f"Error scheduling GitLab sync: {str(e)}", indicator="red")
        return {"status": "error", "error": str(e)}

def perform_full_sync():
    """Perform full GitLab sync in background"""
    start_time = time.time()
    
    try:
        projects = get_all_projects()
        if not projects:
            return
        
        successful_syncs = 0
        failed_syncs = 0
        failed_projects = []
        
        for i, project in enumerate(projects, 1):
            try:
                result = sync_project(project, incremental=False)
                if result["status"] == "success":
                    successful_syncs += 1
                else:
                    failed_syncs += 1
                    failed_projects.append({
                        "name": project.get('name', 'unknown'),
                        "id": project.get('id', 'unknown'),
                        "error": result.get("error", "Unknown error")
                    })
                frappe.db.commit()
                
            except Exception as e:
                failed_syncs += 1
                failed_projects.append({
                    "name": project.get('name', 'unknown'),
                    "id": project.get('id', 'unknown'),
                    "error": str(e)
                })
                frappe.log_error(f"Error processing project {project.get('name', 'unknown')}: {str(e)}")
                continue
        
        total_time = time.time() - start_time
        
        # Log detailed summary
        summary = f"GitLab full sync completed in {total_time:.2f}s. Projects: {successful_syncs} success, {failed_syncs} failed"
        if failed_projects:
            summary += "\n\nFailed Projects:"
            for project in failed_projects:
                summary += f"\n- {project['name']} (ID: {project['id']}): {project['error']}"
        
        frappe.log_error(summary)
        
        # Update sync settings
        settings = get_gitlab_settings()
        settings.last_full_sync = now_datetime()
        settings.save()
        
    except Exception as e:
        frappe.log_error(f"GitLab full sync failed: {str(e)}")
        raise

def perform_incremental_sync():
    """Perform incremental GitLab sync in background"""
    start_time = time.time()
    
    try:
        projects = get_all_projects()
        if not projects:
            return
        
        successful_syncs = 0
        failed_syncs = 0
        failed_projects = []
        
        for i, project in enumerate(projects, 1):
            try:
                result = sync_project(project, incremental=True)
                if result["status"] == "success":
                    successful_syncs += 1
                else:
                    failed_syncs += 1
                    failed_projects.append({
                        "name": project.get('name', 'unknown'),
                        "id": project.get('id', 'unknown'),
                        "error": result.get("error", "Unknown error")
                    })
                frappe.db.commit()
                
            except Exception as e:
                failed_syncs += 1
                failed_projects.append({
                    "name": project.get('name', 'unknown'),
                    "id": project.get('id', 'unknown'),
                    "error": str(e)
                })
                frappe.log_error(f"Error processing project {project.get('name', 'unknown')}: {str(e)}")
                continue
        
        total_time = time.time() - start_time
        
        # Log detailed summary
        summary = f"GitLab incremental sync completed in {total_time:.2f}s. Projects: {successful_syncs} success, {failed_syncs} failed"
        if failed_projects:
            summary += "\n\nFailed Projects:"
            for project in failed_projects:
                summary += f"\n- {project['name']} (ID: {project['id']}): {project['error']}"
        
        frappe.log_error(summary)
        
        # Update sync settings
        settings = get_gitlab_settings()
        settings.last_incremental_sync = now_datetime()
        settings.save()
        
    except Exception as e:
        frappe.log_error(f"GitLab incremental sync failed: {str(e)}")
        raise

# Utility functions for direct access by GitLab ID
def get_gitlab_issue_by_id(gitlab_id):
    """Get GitLab Issue by GitLab ID (direct reference)"""
    gitlab_id = str(gitlab_id)
    if frappe.db.exists("GitLab Issue", gitlab_id):
        return frappe.get_doc("GitLab Issue", gitlab_id)
    return None

def get_gitlab_project_by_id(gitlab_id):
    """Get GitLab Project by GitLab ID (direct reference)"""
    gitlab_id = str(gitlab_id)
    if frappe.db.exists("GitLab Project", gitlab_id):
        return frappe.get_doc("GitLab Project", gitlab_id)
    return None

def link_issue_to_document(gitlab_id, doctype, docname):
    """Link GitLab issue to any Frappe document"""
    gitlab_id = str(gitlab_id)
    if frappe.db.exists("GitLab Issue", gitlab_id):
        doc = frappe.get_doc("GitLab Issue", gitlab_id)
        doc.linked_documents = f"{doctype}: {docname}"
        doc.save()
        return True
    return False

@frappe.whitelist()
def is_job_running():
    """Check if GitLab sync job is queued or started"""
    try:
        # Check for queued or started GitLab sync jobs
        active_jobs = frappe.get_all(
            "RQ Job",
            filters={
                "status": ["in", ["queued", "started"]],
                "job_name": ["in", ["GitLab Full Sync", "GitLab Incremental Sync"]]
            },
            fields=["name", "job_name", "status"]
        )
        
        return {
            "is_running": len(active_jobs) > 0,
            "message": f"Found {len(active_jobs)} GitLab sync job(s) in progress"
        }
        
    except Exception as e:
        frappe.log_error(f"Error checking job status: {str(e)}")
        return {"is_running": False, "error": str(e)}

# Legacy function for backward compatibility
@frappe.whitelist()
def sync_gitlab_data():
    """Legacy function - now schedules background job"""
    return schedule_gitlab_sync("full")
