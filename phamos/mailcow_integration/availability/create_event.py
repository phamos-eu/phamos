from __future__ import annotations
import frappe, requests, base64
from datetime import datetime
from ..utils import get_site_timezone

def _settings(): return frappe.get_single("Mailcow Settings")
def _email(user_id): return frappe.db.get_value("User", user_id, "email")
def _pw(email): return frappe.db.get_value("Mailcow DAV Password", email, "dav_password")
def _auth(email, pw): return {"Authorization": "Basic " + base64.b64encode(f"{email}:{pw}".encode()).decode()}
def _url(base, email, uid): return f"{base.rstrip('/')}/SOGo/dav/{email}/Calendar/personal/{uid}.ics"

def _ics(uid, subject, start_dt, end_dt, description="", location="", seq=1):
    tz = get_site_timezone()
    def fmt(dt: datetime): return dt.strftime("%Y%m%dT%H%M%S")
    desc = (description or "").replace("\r", "\\n").replace("\n", "\\n")
    loc  = (location or "").replace("\n", " ")
    summary = (subject or "").replace("\n", " ")
    return f"""BEGIN:VCALENDAR
            VERSION:2.0
            PRODID:-//ERPNext//your_app//EN
            BEGIN:VEVENT
            UID:{uid}
            SEQUENCE:{seq}
            SUMMARY:{summary}
            DTSTART;TZID={tz}:{fmt(start_dt)}
            DTEND;TZID={tz}:{fmt(end_dt)}
            DESCRIPTION:{desc}
            LOCATION:{loc}
            END:VEVENT
            END:VCALENDAR
            """.strip()

@frappe.whitelist()
def create_sogo_event(title: str, start_iso: str, end_iso: str, description: str = "", location: str = ""):
    import dateutil.parser
    s = _settings()

    owner = frappe.session.user
    email = _email(owner)
    pw = _pw(email)
    if not (email and pw):
        frappe.throw("Missing DAV credentials for organizer")

    start = dateutil.parser.isoparse(start_iso)
    end   = dateutil.parser.isoparse(end_iso)
    uid = frappe.generate_hash(length=16)  # ERPNext docname also works; random is fine too.

    url = _url(s.base_url, email, uid)
    ics = _ics(uid, title, start, end, description, location, seq=1)
    r = requests.put(url, data=ics.encode("utf-8"),
                     headers={**_auth(email, pw), "Content-Type": "text/calendar"},
                     timeout=30)
    if r.status_code not in (200, 201, 204):
        frappe.throw(f"SOGo PUT failed: {r.status_code}: {r.text[:500]}")

    return {"uid": uid, "start": start_iso, "end": end_iso}
