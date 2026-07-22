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
    out: List[Tuple[datetime, datetime]] = []

    # Parse each VEVENT independently. Searching the complete VCALENDAR pairs
    # VTIMEZONE DTSTART values (often historical dates such as 1893) with an
    # event DTEND, which can incorrectly mark the entire calendar as busy.
    event_blocks = re.findall(
        r"BEGIN:VEVENT\s*(.*?)\s*END:VEVENT",
        ics_text,
        flags=re.S | re.I,
    )
    property_pattern = r"^{name}(?P<params>(?:;[^:\r\n]+)*):(?P<value>[0-9T]+Z?)"

    def parse(match) -> datetime:
        import pytz

        value = match.group("value")
        params = match.group("params") or ""
        if value.endswith("Z"):
            return datetime.strptime(value, RFC3339Z).replace(tzinfo=timezone.utc)
        if len(value) == 8:
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)

        parsed = datetime.strptime(value, "%Y%m%dT%H%M%S")
        tzid_match = re.search(r"(?:^|;)TZID=([^;:]+)", params, flags=re.I)
        if tzid_match:
            try:
                return pytz.timezone(tzid_match.group(1)).localize(parsed).astimezone(timezone.utc)
            except pytz.UnknownTimeZoneError:
                pass
        return parsed.replace(tzinfo=timezone.utc)

    for block in event_blocks:
        start_match = re.search(
            property_pattern.format(name="DTSTART"), block, flags=re.M | re.I
        )
        end_match = re.search(
            property_pattern.format(name="DTEND"), block, flags=re.M | re.I
        )
        if start_match and end_match:
            out.append((parse(start_match), parse(end_match)))
    return out

def fetch_busy_intervals_for_mailbox(mailbox_email: str,
                                     window_start_utc: datetime,
                                     window_end_utc: datetime) -> List[Tuple[datetime, datetime]]:
    """REPORT calendar-query to a mailbox SOGo calendar; return merged busy intervals."""
    s = _settings()
    email = (mailbox_email or "").strip()
    if not email:
        raise CalDAVReadError("No mailbox email provided")
    pw = _dav_pw(email)
    if not pw:
        raise CalDAVReadError(f"No DAV app password is configured for {email}")

    url = _calendar_url(s.base_url, email)
    body = _build_report_xml(window_start_utc, window_end_utc, expand=True)
    headers = {
        **_auth(email, pw),
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }
    r = requests.request("REPORT", url, data=body.encode("utf-8"), headers=headers, timeout=30)
    if r.status_code not in (200, 207):
        raise CalDAVReadError(f"CalDAV REPORT failed ({r.status_code}): {r.text[:500]}")

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


def fetch_busy_intervals_from_sogo(user_id: str,
                                   window_start_utc: datetime,
                                   window_end_utc: datetime) -> List[Tuple[datetime, datetime]]:
    """
    REPORT calendar-query to user’s SOGo calendar; return merged busy intervals.
    """
    email = _get_user_email(user_id)
    if not email:
        raise CalDAVReadError(f"No email is configured for User {user_id}")
    return fetch_busy_intervals_for_mailbox(email, window_start_utc, window_end_utc)
