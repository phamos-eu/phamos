import frappe
import requests
from frappe.auth import get_decrypted_password

def get_customer_image_file(customer):
    if not customer.image:
        return None

    file_url = customer.image

    if file_url.startswith("/"):
        site_url = frappe.utils.get_url()
        file_url = f"{site_url}{file_url}"

    try:
        response = requests.get(file_url)
        response.raise_for_status()
        return response.content
    except Exception:
        frappe.log_error("Failed to fetch customer image", frappe.get_traceback())
        return None

def update_gitlab_avatar(group_id=None, project_id=None, customer_doc=None):
    if not customer_doc:
        return

    image_content = get_customer_image_file(customer_doc)
    if not image_content:
        return

    settings = frappe.get_single("GitLab Settings")
    base_url = settings.gitlab_url.rstrip('/')

    headers = {
        "PRIVATE-TOKEN": get_gitlab_headers()["PRIVATE-TOKEN"]
    }

    files = {
        "avatar": ("avatar.png", image_content, "image/png")
    }

    try:
        # ✅ Update Group Avatar
        if group_id:
            requests.put(
                f"{base_url}/api/v4/groups/{group_id}",
                headers=headers,
                files=files
            )

        # ✅ Update Project Avatar
        if project_id:
            requests.put(
                f"{base_url}/api/v4/projects/{project_id}",
                headers=headers,
                files=files
            )

    except Exception:
        frappe.log_error("GitLab Avatar Update Failed", frappe.get_traceback())
        
def update_gitlab_avatar_on_customer(doc, method=None):
    if not doc.image:
        return

    try:
        # 🔹 Find linked group
        group = frappe.db.get_value(
            "GitLab Group",
            {"title": doc.name},
            ["group_id"],
            as_dict=True
        )

        # 🔹 Find linked project
        project = frappe.db.get_value(
            "GitLab Project",
            {"title": doc.name},
            ["project_id"],
            as_dict=True
        )

        update_gitlab_avatar(
            group_id=group["group_id"] if group else None,
            project_id=project["project_id"] if project else None,
            customer_doc=doc
        )

    except Exception:
        frappe.log_error(
            "Customer → GitLab Avatar Sync Failed",
            frappe.get_traceback()
        )

def get_gitlab_headers():
    return {
        "PRIVATE-TOKEN": get_decrypted_password(
            "GitLab Settings",
            "GitLab Settings",
            "access_token"
        ),
        "Content-Type": "application/json"
    }


def create_gitlab_group(group_name, customer_doc=None):
    settings = frappe.get_single("GitLab Settings")
    url = f"{settings.gitlab_url.rstrip('/')}/api/v4/groups"

    data = {
        "name": group_name,
        "path": frappe.scrub(group_name),
        "visibility": "internal"
    }

    files = None
    if customer_doc:
        image_content = get_customer_image_file(customer_doc)
        if image_content:
            files = {
                "avatar": ("avatar.png", image_content, "image/png")
            }

    response = requests.post(
        url,
        headers={"PRIVATE-TOKEN": get_gitlab_headers()["PRIVATE-TOKEN"]},
        data=data,
        files=files
    )

    response.raise_for_status()
    return response.json() 


def create_gitlab_project(project_name, group_id, customer_doc=None):
    settings = frappe.get_single("GitLab Settings")
    base_url = settings.gitlab_url.rstrip('/')
    url = f"{base_url}/api/v4/projects"

    data = {
        "name": project_name,
        "path": frappe.scrub(project_name),
        "namespace_id": str(group_id),
        "visibility": "internal",
        "initialize_with_readme": "true"
    }

    files = None
    if customer_doc:
        image_content = get_customer_image_file(customer_doc)
        if image_content:
            files = {
                "avatar": ("avatar.png", image_content, "image/png")
            }

    response = requests.post(
        url,
        headers={"PRIVATE-TOKEN": get_gitlab_headers()["PRIVATE-TOKEN"]},
        data=data,
        files=files
    )

    response.raise_for_status()
    project = response.json()
    project_id = project["id"]

    # ── Webhook register for new project ──
    try:
        webhook_secret = get_decrypted_password(
            "GitLab Settings", "GitLab Settings", "webhook_secret"
        )
    except Exception:
        webhook_secret = None

    if settings.webhook_base_url:
        webhook_url = f"{settings.webhook_base_url}/api/method/phamos.gitlab_integration.gitlab_utils.gitlab_webhook_receiver"

        webhook_payload = {
            "url": webhook_url,
            "issues_events": True,
            "enable_ssl_verification": False,
        }
        if webhook_secret:
            webhook_payload["token"] = webhook_secret

        hook_resp = requests.post(
            f"{base_url}/api/v4/projects/{project_id}/hooks",
            json=webhook_payload,
            headers=get_gitlab_headers()
        )

        if hook_resp.status_code != 201:
            frappe.log_error(
                title="GitLab Webhook Register Failed",
                message=f"Project: {project_name}, Response: {hook_resp.text}"
            )

    return project


def create_group_and_project_if_not_exists(doc, method=None):
    customer_name = doc.customer
    if not customer_name:
        return

    try:
        customer_doc = frappe.get_doc("Customer", customer_name)

        group = create_gitlab_group(customer_name, customer_doc)

        project = create_gitlab_project(
            customer_name,
            group["id"],
            customer_doc
        )

        frappe.msgprint("Group & Project with image created successfully")

    except Exception:
        frappe.log_error(
            title="GitLab Create Error",
            message=frappe.get_traceback()
        )
        frappe.msgprint("Error while creating GitLab resources")