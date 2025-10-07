from __future__ import annotations
import base64, requests
import frappe
from frappe.utils.password import get_decrypted_password

class CalDAVError(frappe.ValidationError): pass

def settings():
    s = frappe.get_single("Mailcow Settings")
    return s

def organizer_email() -> str | None:
    if frappe.session.user == "Administrator":
        frappe.throw("You're logged in as Administrator; cannot determine organizer email.")
    else:
        return frappe.session.user

def dav_password(email: str) -> str | None:
    dav_doc = frappe.db.get_all("Mailcow DAV Password", filters={"user": email}, pluck="name")[0]
    
    return get_decrypted_password(
        doctype="Mailcow DAV Password",
        name=dav_doc,
        fieldname="dav_password",
    )

def _auth(email, pw):
    token = base64.b64encode(f"{email}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}

def calendar_item_url(base_url: str, email: str, uid: str) -> str:
    base = base_url.rstrip("/")
    return f"{base}/SOGo/dav/{email}/Calendar/personal/{uid}.ics"

def put_ics(uid: str, ics: str, acting_user_id: str):
    s = settings()
    email = organizer_email()
    if not email: return
    pw = dav_password(email)
    if not pw:
        frappe.log_error(f"No DAV app password for {email}", "CalDAV PUT")
        return
    url = calendar_item_url(s.base_url, email, uid)
    r = requests.put(
        url, data=ics.encode("utf-8"),
        headers={"Content-Type": "text/calendar", "If-None-Match": "*"},
        auth=(email, pw),
        timeout=30
    )
    if r.status_code not in (200, 201, 204):
        frappe.log_error(f"{r.status_code} {r.text}", "CalDAV PUT")

def delete_ics(uid: str):
    s = settings()
    email = organizer_email()
    if not email: return
    pw = dav_password(email)
    if not pw: return
    url = calendar_item_url(s.base_url, email, uid)
    r = requests.delete(url, auth=(email, pw), timeout=15)
    # ignore 404; log other failures
    if r.status_code not in (200, 204, 404):
        frappe.log_error(f"{r.status_code} {r.text}", "CalDAV DELETE")
