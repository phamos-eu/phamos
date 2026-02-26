from __future__ import annotations
import base64, requests, re
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict
from ..caldav.client import dav_password as _dav_pw
import frappe

RFC3339Z = "%Y%m%dT%H%M%SZ"  # UTC timestamps for REPORT time-range

class CalDAVReadError(frappe.ValidationError): pass

def _settings():
    s = frappe.get_single("Mailcow Settings")
    if not s.base_url:
        raise CalDAVReadError("Missing base_url")
    return s

def _get_user_email(user_id: str) -> str | None:
    return frappe.db.get_value("User", user_id, "email")

def _auth(email: str, pw: str) -> Dict[str, str]:
    tok = base64.b64encode(f"{email}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {tok}"}

def _calendar_url(base_url: str, email: str) -> str:
    return f"{base_url.rstrip('/')}/SOGo/dav/{email}/Calendar/personal/"

def _build_report_xml(start_utc: datetime, end_utc: datetime, expand: bool = True) -> str:
    # Ask for DTSTART/DTEND and recurrence expansion within the window.
    start = start_utc.strftime(RFC3339Z)
    end = end_utc.strftime(RFC3339Z)
    expand_xml = f'<c:expand start="{start}" end="{end}"/>' if expand else ""
    return f"""<?xml version="1.0" encoding="utf-8" ?>
        <c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
        <d:prop>
            <d:getetag/>
            <c:calendar-data>
            <c:comp name="VCALENDAR">
                <c:comp name="VEVENT">
                <c:prop name="UID"/>
                <c:prop name="DTSTART"/>
                <c:prop name="DTEND"/>
                <c:prop name="DURATION"/>
                <c:prop name="RRULE"/>
                <c:prop name="RDATE"/>
                <c:prop name="EXDATE"/>
                </c:comp>
            </c:comp>
            {expand_xml}
            </c:calendar-data>
        </d:prop>
        <c:filter>
            <c:comp-filter name="VCALENDAR">
            <c:comp-filter name="VEVENT">
                <c:time-range start="{start}" end="{end}"/>
            </c:comp-filter>
            </c:comp-filter>
        </c:filter>
        </c:calendar-query>""".strip()

def _parse_ics_blocks(multistatus_xml: str) -> List[str]:
    # Very lightweight extraction of <cal:calendar-data>…ICS…</cal:calendar-data>
    # We avoid extra deps; SOGo returns each object’s ICS inside that element.
    return re.findall(r"<(?:[^:>]+:)?calendar-data>(.*?)</(?:[^:>]+:)?calendar-data>",
                      multistatus_xml, flags=re.S|re.I)

def _extract_dt_pairs(ics_text: str) -> List[Tuple[datetime, datetime]]:
    """
    Extract DTSTART/DTEND pairs from VCALENDAR/VEVENT. Handles single instances.
    Times are usually returned expanded by server when we used <c:expand>.
    """
    # capture lines; tolerate TZID or Zulu
    dtstart = re.findall(r"^DTSTART(?:;TZID=[^\r\n:]+)?:([0-9T]+Z?)", ics_text, flags=re.M)
    dtend   = re.findall(r"^DTEND(?:;TZID=[^\r\n:]+)?:([0-9T]+Z?)",   ics_text, flags=re.M)
    out: List[Tuple[datetime, datetime]] = []
    for a, b in zip(dtstart, dtend):
        def parse(x: str) -> datetime:
            if x.endswith("Z"):
                return datetime.strptime(x, RFC3339Z).replace(tzinfo=timezone.utc)
            # naive local; treat as UTC for union—SOGo usually returns with TZ or Z
            return datetime.strptime(x, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        out.append((parse(a), parse(b)))
    return out

def fetch_busy_intervals_from_sogo(user_id: str,
                                   window_start_utc: datetime,
                                   window_end_utc: datetime) -> List[Tuple[datetime, datetime]]:
    """
    REPORT calendar-query to user’s SOGo calendar; return merged busy intervals.
    """
    s = _settings()
    email = _get_user_email(user_id)
    if not email: return []
    pw = _dav_pw(email)
    if not pw:
        frappe.log_error(f"No DAV app password for {email}", "CalDAV read")
        return []

    url = _calendar_url(s.base_url, email)
    body = _build_report_xml(window_start_utc, window_end_utc, expand=True)
    headers = {
        **_auth(email, pw),
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }
    r = requests.request("REPORT", url, data=body.encode("utf-8"), headers=headers, timeout=30)
    if r.status_code not in (200, 207):
        frappe.log_error(f"{r.status_code} {r.text[:500]}", "CalDAV REPORT")
        return []

    intervals: List[Tuple[datetime, datetime]] = []
    for ics in _parse_ics_blocks(r.text):
        intervals.extend(_extract_dt_pairs(ics))

    # merge overlaps
    intervals.sort(key=lambda x: x[0])
    merged: List[Tuple[datetime, datetime]] = []
    for srt, end in intervals:
        if not merged or srt > merged[-1][1]:
            merged.append((srt, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged
