from __future__ import annotations
import base64, requests, re
from urllib.parse import urljoin
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


def _calendar_home_url(base_url: str, email: str) -> str:
    return f"{base_url.rstrip('/')}/SOGo/dav/{email}/Calendar/"


def _discover_calendar_urls(base_url: str, email: str, headers: Dict[str, str]) -> List[str]:
    """Return available calendar collection URLs for the user calendar home."""
    home_url = _calendar_home_url(base_url, email)
    propfind_body = """<?xml version=\"1.0\" encoding=\"utf-8\" ?>
<d:propfind xmlns:d=\"DAV:\">
  <d:prop>
    <d:resourcetype/>
  </d:prop>
</d:propfind>"""

    propfind_headers = {
        **headers,
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }

    resp = requests.request(
        "PROPFIND",
        home_url,
        data=propfind_body.encode("utf-8"),
        headers=propfind_headers,
        timeout=30,
    )
    if resp.status_code not in (200, 207):
        return [_calendar_url(base_url, email)]

    urls: List[str] = []
    matches = re.findall(
        r"<d:response>.*?<d:href>(?P<href>.*?)</d:href>.*?<d:resourcetype>.*?<[^>]*calendar[^>]*>.*?</d:resourcetype>.*?</d:response>",
        resp.text,
        flags=re.S | re.I,
    )

    for href in matches:
        decoded_href = href.replace("&amp;", "&")
        absolute = urljoin(base_url.rstrip("/") + "/", decoded_href.lstrip("/"))
        if not absolute.endswith("/"):
            absolute = absolute + "/"
        urls.append(absolute)

    if not urls:
        return [_calendar_url(base_url, email)]

    # Preserve order while deduplicating.
    return list(dict.fromkeys(urls))

def _build_report_xml(start_utc: datetime, end_utc: datetime, expand: bool = True) -> str:
    # Ask for DTSTART/DTEND and recurrence expansion within the window.
    start = start_utc.strftime(RFC3339Z)
    end = end_utc.strftime(RFC3339Z)
    expand_xml = f'<c:expand start="{start}" end="{end}"/>' if expand else ""
    calendar_data_xml = (
        f"<c:calendar-data>{expand_xml}</c:calendar-data>"
        if expand
        else """<c:calendar-data>
            <c:comp name=\"VCALENDAR\">
                <c:comp name=\"VEVENT\">
                    <c:prop name=\"UID\"/>
                    <c:prop name=\"DTSTART\"/>
                    <c:prop name=\"DTEND\"/>
                    <c:prop name=\"DURATION\"/>
                    <c:prop name=\"RRULE\"/>
                    <c:prop name=\"RDATE\"/>
                    <c:prop name=\"EXDATE\"/>
                </c:comp>
            </c:comp>
        </c:calendar-data>"""
    )
    return f"""<?xml version="1.0" encoding="utf-8" ?>
        <c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
        <d:prop>
            <d:getetag/>
            {calendar_data_xml}
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
    property_pattern = r"^{name}(?P<params>(?:;[^:\r\n]+)*):(?P<value>[^\r\n]+)"

    def parse(match) -> datetime:
        import pytz

        value = (match.group("value") or "").strip()
        params = match.group("params") or ""

        if len(value) == 8 and value.isdigit():
            return datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)

        normalized = re.sub(r"\.(\d+)", "", value)

        # Handle explicit UTC timestamps.
        if normalized.endswith("Z"):
            for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%MZ"):
                try:
                    return datetime.strptime(normalized, fmt).replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        # Handle explicit numeric UTC offsets, e.g. +0200 / -0530.
        if re.search(r"[+-]\d{4}$", normalized):
            for fmt in ("%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%z"):
                try:
                    return datetime.strptime(normalized, fmt).astimezone(timezone.utc)
                except ValueError:
                    pass

        parsed = None
        for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                break
            except ValueError:
                continue
        if parsed is None:
            raise ValueError(f"Unsupported iCalendar datetime format: {value}")

        tzid_match = re.search(r"(?:^|;)TZID=([^;:]+)", params, flags=re.I)
        if tzid_match:
            try:
                return pytz.timezone(tzid_match.group(1)).localize(parsed).astimezone(timezone.utc)
            except pytz.UnknownTimeZoneError:
                pass
        return parsed.replace(tzinfo=timezone.utc)

    def parse_duration_iso(duration_text: str) -> timedelta | None:
        # Minimal ISO-8601 duration parser for iCalendar DURATION values.
        # Supports forms like PT30M, PT1H, P1DT2H30M, -PT15M.
        match = re.fullmatch(
            r"(?P<sign>-)?P(?:(?P<weeks>\d+)W)?(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
            duration_text,
            flags=re.I,
        )
        if not match:
            return None

        weeks = int(match.group("weeks") or 0)
        days = int(match.group("days") or 0)
        hours = int(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        seconds = int(match.group("seconds") or 0)
        delta = timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds)
        return -delta if match.group("sign") else delta

    for block in event_blocks:
        # Unfold folded iCalendar lines (RFC 5545) before extracting properties.
        block = re.sub(r"\r?\n[ \t]", "", block)

        start_match = re.search(
            property_pattern.format(name="DTSTART"), block, flags=re.M | re.I
        )
        end_match = re.search(
            property_pattern.format(name="DTEND"), block, flags=re.M | re.I
        )

        if not start_match:
            continue

        try:
            start_dt = parse(start_match)
        except ValueError:
            continue
        if end_match:
            try:
                out.append((start_dt, parse(end_match)))
            except ValueError:
                pass
            continue

        duration_match = re.search(r"^DURATION(?:;[^:\r\n]+)*:(?P<value>[^\r\n]+)", block, flags=re.M | re.I)
        if duration_match:
            duration_delta = parse_duration_iso(duration_match.group("value").strip())
            if duration_delta and duration_delta.total_seconds() > 0:
                out.append((start_dt, start_dt + duration_delta))
    return out

def fetch_busy_intervals_from_sogo(user_id: str,
                                   window_start_utc: datetime,
                                   window_end_utc: datetime,
                                   merge_overlaps: bool = True,
                                   include_all_calendars: bool = False) -> List[Tuple[datetime, datetime]]:
    """
    REPORT calendar-query to user’s SOGo calendar; return merged busy intervals.
    """
    s = _settings()
    email = _get_user_email(user_id)
    if not email:
        raise CalDAVReadError(f"No email is configured for User {user_id}")
    pw = _dav_pw(email)
    if not pw:
        raise CalDAVReadError(f"No DAV app password is configured for {email}")

    body = _build_report_xml(window_start_utc, window_end_utc, expand=True)
    headers = {
        **_auth(email, pw),
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8",
    }

    if include_all_calendars:
        calendar_urls = _discover_calendar_urls(s.base_url, email, _auth(email, pw))
    else:
        calendar_urls = [_calendar_url(s.base_url, email)]

    intervals: List[Tuple[datetime, datetime]] = []
    failures: List[str] = []
    for url in calendar_urls:
        r = requests.request("REPORT", url, data=body.encode("utf-8"), headers=headers, timeout=30)
        if r.status_code not in (200, 207):
            failures.append(f"{url} ({r.status_code})")
            continue
        for ics in _parse_ics_blocks(r.text):
            intervals.extend(_extract_dt_pairs(ics))

    if not intervals and failures:
        raise CalDAVReadError(f"CalDAV REPORT failed for calendar collections: {', '.join(failures)}")

    intervals.sort(key=lambda x: x[0])

    if not merge_overlaps:
        return intervals

    # merge overlaps
    merged: List[Tuple[datetime, datetime]] = []
    for srt, end in intervals:
        if not merged or srt > merged[-1][1]:
            merged.append((srt, end))
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged
