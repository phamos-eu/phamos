
from __future__ import annotations
import frappe
import html
import re
from ..utils import get_site_timezone
from datetime import datetime, timezone
from frappe.utils import get_datetime
from frappe.utils import strip_html


def _fmt(dt: datetime) -> str:
    # local datetime as YYYYMMDDTHHMMSS (SOGo accepts TZID on DTSTART/DTEND)
    if not isinstance(dt, datetime):
        dt = get_datetime(dt)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y%m%dT%H%M%S")


def vevent(uid: str, seq: int, subject: str, starts_on, ends_on,
           description: str = "", location: str = "Online", 
           attendees_to: str = "", attendees_cc: str = "", attendees_bcc: str = "",
           attendee_role_map: dict[str, str] | None = None) -> str:
    tz = get_site_timezone()
    summary = (subject or "").replace("\n", " ")
    desc = strip_html(description or "")
    loc = (location or "").replace("\n", " ")

    # Build base ICS
    ics_lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//ERPNext//phamos//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID={tz}:{_fmt(starts_on)}",
        f"DTEND;TZID={tz}:{_fmt(ends_on)}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{loc}",
        f"ORGANIZER;CN={frappe.session.user}:mailto:{frappe.session.user}",
    ]

    # Parse and add attendees
    from email.utils import getaddresses
    
    # Add TO recipients with RSVP enabled (role defaults to optional)
    if attendees_to:
        to_list = [email.strip() for email in attendees_to.split(",") if email.strip()]
        for email_addr in to_list:
            # Extract email from "Name <email>" format if present
            _, addr = getaddresses([email_addr])[0] if getaddresses([email_addr]) else ("", email_addr)
            if addr:
                role = (attendee_role_map or {}).get(addr.lower(), "OPT-PARTICIPANT")
                ics_lines.append(f"ATTENDEE;ROLE={role};PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{addr}")
    
    # Add CC recipients with RSVP enabled (role defaults to optional)
    if attendees_cc:
        cc_list = [email.strip() for email in attendees_cc.split(",") if email.strip()]
        for email_addr in cc_list:
            _, addr = getaddresses([email_addr])[0] if getaddresses([email_addr]) else ("", email_addr)
            if addr:
                role = (attendee_role_map or {}).get(addr.lower(), "OPT-PARTICIPANT")
                ics_lines.append(f"ATTENDEE;ROLE={role};PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{addr}")
    
    # BCC recipients are NOT added as attendees (they receive the email but not the calendar invite)
    # This maintains the "blind" nature of BCC - they get the email notification only

    # Close the event
    ics_lines.extend([
        "STATUS:CONFIRMED",
        f"SEQUENCE:{seq}",
        "END:VEVENT",
        "END:VCALENDAR"
    ])

    return "\r\n".join(ics_lines) + "\r\n"


def vtodo(uid: str, seq: int, title: str, due=None, status=None,
          description: str = "", priority: int | None = None) -> str:
    tz = get_site_timezone()
    summary = (title or "").replace("\n", " ")
    desc = (description or "").replace("\r", "\\n").replace("\n", "\\n")
    due_line = f"\nDUE;TZID={tz}:{_fmt(due)}" if due else ""
    status_line = f"\nSTATUS:{status}" if status else ""
    prio_line = f"\nPRIORITY:{priority}" if priority else ""
    percent_complete = "100" if status == "COMPLETED" else "0"

    status_mapping = {
        "Not Started": "NEEDS-ACTION",
        "In Progress": "IN-PROCESS",
        "Completed": "COMPLETED",
        "Cancelled": "CANCELLED"
    }
    if status in status_mapping:
        status_line = status_mapping[status]
    
    ics =  (
        "BEGIN:VCALENDAR\r\n"
        "PRODID:-//ERPNext//phamos//EN\r\n"
        "VERSION:2.0\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VTODO\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
        f"DUE;TZID={tz}:{_fmt(due_line)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        f"STATUS:{status_line}\r\n"
        f"PRIORITY:{prio_line}\r\n"
        f"PERCENT-COMPLETE:{percent_complete}\r\n"
        f"ORGANIZER;CN={frappe.session.user}:mailto:{frappe.session.user}\r\n"
        f"ATTENDEE;CN={frappe.session.user};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{frappe.session.user}\r\n"
        f"SEQUENCE:{seq}\r\n"
        "END:VTODO\r\n"
        "END:VCALENDAR\r\n"
    )

    return ics.strip()

  
