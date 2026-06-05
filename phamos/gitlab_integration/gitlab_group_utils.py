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
        "PRIVATE-TOKEN": get_decrypted_password(
        "GitLab Settings", "GitLab Settings", "access_token"
        )
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

    doc_before = doc.get_doc_before_save()
    if doc_before and doc_before.image == doc.image:
        return

    try:
        group = frappe.db.get_value(
            "GitLab Group",
            {"title": doc.name},
            ["name", "group_id"],
            as_dict=True
        )

        if group:
            update_gitlab_avatar(
                group_id=group["group_id"],
                project_id=None,
                customer_doc=doc
            )

            projects = frappe.db.get_all(
                "GitLab Project",
                {"group": group["name"]},
                ["project_id"]
            )

            for project in projects:
                update_gitlab_avatar(
                    group_id=None,
                    project_id=project["project_id"],
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


@frappe.whitelist()
def create_gitlab_group_for_customer(customer_name, gitlab_group_name=None):
    if not customer_name:
        frappe.throw("Customer name is required")

    gitlab_group_name = gitlab_group_name or customer_name

    try:
        customer_doc = frappe.get_doc("Customer", customer_name)

        # ✅ Check: customer group already exist?
        existing_group = frappe.db.get_value(
            "GitLab Group",
            {"customer": customer_name},
            ["title", "web_url"],
            as_dict=True
        )

        if existing_group:
            frappe.throw(
                f"GitLab Group already exists for this customer.<br><br>"
                f"<b>Group Name:</b> {existing_group.title}<br>"
                f"<b>URL:</b> <a href='{existing_group.web_url}' target='_blank'>{existing_group.web_url}</a>",
                title="Group Already Exists"
            )

        # GitLab group create with edited name
        group = create_gitlab_group(gitlab_group_name, customer_doc)

        # GitLab Group record in ERP
        if not frappe.db.exists("GitLab Group", {"title": gitlab_group_name}):
            gitlab_group_doc = frappe.get_doc({
                "doctype": "GitLab Group",
                "title": gitlab_group_name,
                "group_id": group["id"],
                "web_url": group["web_url"],
                "full_path": group["full_path"],
                "path": group["path"],
                "customer": customer_name,
            })
            gitlab_group_doc.insert(ignore_permissions=True)
            frappe.db.commit()

        frappe.msgprint(f"GitLab Group '{gitlab_group_name}' successfully created!")

    except frappe.ValidationError:
        raise  # to pass frappe.throw error

    except Exception:
        frappe.log_error(
            title="GitLab Group Create Error",
            message=frappe.get_traceback()
        )
        frappe.throw("Error while creating GitLab Group")

@frappe.whitelist()
def create_gitlab_project_for_implementation(implementation_name, gitlab_project_name=None):
    if not implementation_name:
        frappe.throw("Implementation name is required")

    gitlab_project_name = gitlab_project_name or implementation_name

    try:
        impl_doc = frappe.get_doc("Implementation", implementation_name)
        customer_name = impl_doc.customer

        if not customer_name:
            frappe.throw("No customer linked to this Implementation")

        customer_doc = frappe.get_doc("Customer", customer_name)

        gitlab_group = frappe.db.get_value(
            "GitLab Group",
            {"title": customer_name},
            ["group_id"],
            as_dict=True
        )

        if not gitlab_group:
            frappe.throw(f"No GitLab Group found for customer '{customer_name}'. Please create the group first.")

        # ✅ Check: implementation already has a project linked
        existing_project = frappe.db.get_value(
            "GitLab Project",
            {"implementation": implementation_name},
            ["title", "web_url"],
            as_dict=True
        )

        if existing_project:
            frappe.throw(
                f"GitLab Project already exists for this Implementation.<br><br>"
                f"<b>Project Name:</b> {existing_project.title}<br>"
                f"<b>URL:</b> <a href='{existing_project.web_url}' target='_blank'>{existing_project.web_url}</a>",
                title="Project Already Exists"
            )

        project = create_gitlab_project(
            gitlab_project_name,
            gitlab_group["group_id"],
            customer_doc
        )

        if not frappe.db.exists("GitLab Project", {"title": gitlab_project_name}):
            group_link = None
            namespace = project.get("namespace", {})
            if namespace.get("kind") == "group":
                group_link = frappe.db.get_value(
                    "GitLab Group",
                    {"group_id": namespace["id"]},
                    "name"
                )

            gitlab_project_doc = frappe.get_doc({
                "doctype": "GitLab Project",
                "title": gitlab_project_name,
                "project_id": project["id"],
                "namespace": project.get("path_with_namespace"),
                "web_url": project["web_url"],
                "group": group_link or None,
                "implementation": implementation_name, 
            })
            gitlab_project_doc.insert(ignore_permissions=True)
            frappe.db.commit()

        frappe.msgprint(f"GitLab Project '{gitlab_project_name}' successfully created!")

    except frappe.ValidationError:
        raise
    except Exception:
        frappe.log_error(
            title="GitLab Project Create Error",
            message=frappe.get_traceback()
        )
        frappe.throw("Error while creating GitLab Project")