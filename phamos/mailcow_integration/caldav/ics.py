
from __future__ import annotations
import frappe
import html
import re
from ..utils import get_site_timezone
from datetime import datetime, timedelta, timezone
from email.utils import getaddresses
from frappe.utils import get_datetime, getdate, strip_html


def _escape_ics_text(value: str) -> str:
    # RFC5545 text escaping: backslash, semicolon, comma, and newline.
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _fmt(dt: datetime) -> str:
    # local datetime as YYYYMMDDTHHMMSS (SOGo accepts TZID on DTSTART/DTEND)
    if not isinstance(dt, datetime):
        dt = get_datetime(dt)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y%m%dT%H%M%S")


ALLOWED_STATUS = ("CONFIRMED", "TENTATIVE", "CANCELLED")


def _fmt_date(value) -> str:
    # all-day events carry a date only (VALUE=DATE): no time, no TZID
    return getdate(value).strftime("%Y%m%d")


def _attendee_lines(attendees_csv: str, attendee_role_map: dict[str, str] | None) -> list[str]:
    """ATTENDEE lines for a comma-separated list; "Name <email>" entries keep only the email.

    RSVP is requested and the role defaults to optional unless the map says otherwise.
    """
    lines = []
    for email_addr in [e.strip() for e in (attendees_csv or "").split(",") if e.strip()]:
        parsed = getaddresses([email_addr])
        addr = parsed[0][1] if parsed else email_addr
        if addr:
            role = (attendee_role_map or {}).get(addr.lower(), "OPT-PARTICIPANT")
            lines.append(f"ATTENDEE;ROLE={role};PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{addr}")
    return lines


def vevent(uid: str, seq: int, subject: str, starts_on, ends_on,
           description: str = "", location: str = "Online", 
           attendees_to: str = "", attendees_cc: str = "", attendees_bcc: str = "",
           attendee_role_map: dict[str, str] | None = None,
           organizer_email: str | None = None,
           recurrence_rule: str | None = None,
           all_day: bool = False,
           status: str = "CONFIRMED",
           url: str | None = None,
           method: str | None = None) -> str:
    """Build one VEVENT as iCalendar text for SOGo.

    Milestone 68 additions, all defaulted so older callers are unchanged:
    - `all_day`: DTSTART/DTEND as VALUE=DATE; the DTEND date is exclusive, so a leave from
      3 to 5 November ends on 6 November (that is how every calendar shows the last day).
    - `status`: CONFIRMED, TENTATIVE (drafts) or CANCELLED.
    - `url`: a URL property, which SOGo and phones show as a clickable link.
    - `method`: REQUEST when attendees are invited, otherwise PUBLISH. SOGo treats a REQUEST
      without attendees as a foreign invitation, so the default is derived from the attendees.
    """
    tz = get_site_timezone()
    summary = _escape_ics_text((subject or "").replace("\n", " "))
    desc = _escape_ics_text(strip_html(description or ""))
    loc = _escape_ics_text((location or "").replace("\n", " "))

    organizer = _escape_ics_text((organizer_email or frappe.session.user or "").strip())

    # BCC recipients are NOT added as attendees (they receive the email but not the calendar
    # invite). This maintains the "blind" nature of BCC: they get the email notification only.
    attendees = _attendee_lines(attendees_to, attendee_role_map) + _attendee_lines(attendees_cc, attendee_role_map)

    method = (method or ("REQUEST" if attendees else "PUBLISH")).upper()
    status = (status or "CONFIRMED").upper()
    if status not in ALLOWED_STATUS:
        status = "CONFIRMED"

    if all_day:
        end_exclusive = getdate(ends_on or starts_on) + timedelta(days=1)
        date_lines = [
            f"DTSTART;VALUE=DATE:{_fmt_date(starts_on)}",
            f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}",
        ]
    else:
        date_lines = [
            f"DTSTART;TZID={tz}:{_fmt(starts_on)}",
            f"DTEND;TZID={tz}:{_fmt(ends_on)}",
        ]

    ics_lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//ERPNext//phamos//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{method}",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        *date_lines,
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        f"LOCATION:{loc}",
    ]
    if url:
        # URI values are not text-escaped (RFC 5545 section 3.3.13)
        ics_lines.append(f"URL:{url}")
    ics_lines.append(f"ORGANIZER;CN={organizer}:mailto:{organizer}")
    ics_lines.extend(attendees)

    if recurrence_rule:
        ics_lines.append(f"RRULE:{recurrence_rule}")

    # Close the event
    ics_lines.extend([
        f"STATUS:{status}",
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

  
