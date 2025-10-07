
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
           description: str = "", location: str = "Online") -> str:
    tz = get_site_timezone()
    summary = (subject or "").replace("\n", " ")
    desc = strip_html(description or "")
    loc = (location or "").replace("\n", " ")

    ics =  (
        "BEGIN:VCALENDAR\r\n"
        "PRODID:-//ERPNext//phamos//EN\r\n"
        "VERSION:2.0\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:REQUEST\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}\r\n"
        f"DTSTART;TZID={tz}:{_fmt(starts_on)}\r\n"
        f"DTEND;TZID={tz}:{_fmt(ends_on)}\r\n"
        f"SUMMARY:{summary}\r\n"
        f"DESCRIPTION:{desc}\r\n"
        f"LOCATION:{loc}\r\n"
        f"ORGANIZER;CN={frappe.session.user}:mailto:{frappe.session.user}\r\n"
        f"ATTENDEE;CN={frappe.session.user};ROLE=REQ-PARTICIPANT;RSVP=TRUE:mailto:{frappe.session.user}\r\n"
        f"STATUS:CONFIRMED\r\n"
        f"SEQUENCE:{seq}\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics.strip()


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

  
