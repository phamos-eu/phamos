import frappe
import requests
from .utils import _headers, get_mailbox, generate_password
from frappe.utils.password import get_decrypted_password, set_encrypted_password

def create_app_password(user_email, app_name, app_password, protocols=("dav_access",)):    
    base = frappe.db.get_single_value("Mailcow Settings", "base_url").rstrip("/")
    payload = {
        "active": True,
        "username": user_email,
        "app_name": app_name,
        "app_passwd": app_password,
        "app_passwd2": app_password,
        "protocols": list(protocols)
    }
    url = f"{base}/api/v1/add/app-passwd"
    r = requests.post(url, json=payload, headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


@frappe.whitelist()
def generate_dav_password(username):
    # check if mailbox exists and return if it does not exist
    mailbox_res = get_mailbox(username)
    if len(mailbox_res.json()) == 0:
        frappe.throw(f"Mailbox not yet provisioned for this user <strong>{username}</strong>")
        return
    dav_password = generate_password(16)
    # Create and Save App Password
    if not frappe.db.exists({'doctype': 'Mailcow DAV Password', 'user': username}):
        create_app_password(user_email=username, app_name='ERPNext', app_password=dav_password)
        dav_doc = frappe.get_doc({'doctype':'Mailcow DAV Password', 'user': username, 'dav_password': dav_password,'reset_password': generate_password(13)})
        dav_doc.insert()
    else:
        dav_doc_name = frappe.db.get_value('Mailcow DAV Password', {'user': username}, 'name')
        dav_doc = frappe.get_doc('Mailcow DAV Password', dav_doc_name)
        create_app_password(user_email=username, app_name='ERPNext', app_password=dav_password)
        dav_doc.user = username
        dav_doc.dav_password = dav_password
        dav_doc.save()

    return {"status": "ok", "user": username, "dav_password": dav_password}