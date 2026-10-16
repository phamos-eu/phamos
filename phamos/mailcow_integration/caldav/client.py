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
    rows = frappe.db.get_all("Mailcow DAV Password", filters={"user": email}, pluck="name")
    if not rows:
        return None
    dav_doc = rows[0]
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

def calendar_email(acting_user_id: str | None) -> str:
    """Mailbox of the calendar owner: the given user, else the session user."""
    email = None
    if acting_user_id:
        email = frappe.db.get_value("User", acting_user_id, "email") or acting_user_id
    if not email:
        email = organizer_email()
    if not email:
        raise CalDAVError("Could not determine the calendar owner email.")
    return email

def put_ics(uid: str, ics: str, acting_user_id: str, create_only: bool = False):
    """Create or update a calendar object.

    `create_only` sends `If-None-Match: *`, so SOGo refuses to overwrite an existing object with
    the same UID. Use it only for the first push of a UID this system generated; updates must
    go without it, or SOGo answers 412 and the change never arrives (#1558).
    """
    s = settings()
    email = calendar_email(acting_user_id)
    pw = dav_password(email)
    if not pw:
        raise CalDAVError(f"No DAV app password is configured for {email}.")
    url = calendar_item_url(s.base_url, email, uid)
    headers = {"Content-Type": "text/calendar"}
    if create_only:
        headers["If-None-Match"] = "*"
    r = requests.put(
        url, data=ics.encode("utf-8"),
        headers=headers,
        auth=(email, pw),
        timeout=30
    )
    if r.status_code not in (200, 201, 204):
        raise CalDAVError(f"SOGo calendar update failed ({r.status_code}): {r.text[:500]}")
    return {"uid": uid, "calendar_user": acting_user_id, "email": email}

def delete_ics(uid: str, acting_user_id: str | None = None):
    """Delete a calendar object from the owner's calendar (not the session user's, #1558)."""
    s = settings()
    email = calendar_email(acting_user_id)
    pw = dav_password(email)
    if not pw: return
    url = calendar_item_url(s.base_url, email, uid)
    r = requests.delete(url, auth=(email, pw), timeout=15)
    # ignore 404; log other failures
    if r.status_code not in (200, 204, 404):
        frappe.log_error(f"{r.status_code} {r.text}", "CalDAV DELETE")
