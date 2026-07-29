from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import getdate

from phamos.mailcow_integration.availability.caldav_read import fetch_busy_intervals_from_sogo
from phamos.mailcow_integration.utils import get_site_timezone


@frappe.whitelist()
def get_logged_in_employee():
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user},
        ["name", "employee_name"],
        as_dict=True,
    )
    return employee or {}


def _resolve_calendar_user(employee: str | None) -> str:
    """Resolve the User account whose calendar should be queried."""
    if not employee:
        frappe.throw("Employee is required.")

    user_id = frappe.db.get_value("Employee", employee, "user_id")
    if not user_id:
        frappe.throw(f"Employee {employee} is not linked to a User.")
    return user_id


def _work_window_for_day(day_local, tz, work_start: str, work_end: str):
    sh, sm = map(int, work_start.split(":"))
    eh, em = map(int, work_end.split(":"))

    start_local = tz.localize(datetime(day_local.year, day_local.month, day_local.day, sh, sm, 0))
    end_local = tz.localize(datetime(day_local.year, day_local.month, day_local.day, eh, em, 0))
    if end_local <= start_local:
        end_local = start_local + timedelta(hours=1)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _day_bounds_utc(day_local, tz):
    start_local = tz.localize(datetime(day_local.year, day_local.month, day_local.day, 0, 0, 0))
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _to_local_calendar_iso(value_utc: datetime, tz) -> str:
    """Return local wall-clock ISO without UTC offset for stable FullCalendar display."""
    return value_utc.astimezone(tz).strftime("%Y-%m-%dT%H:%M:%S")


def _subtract_busy_from_window(busy, window_start, window_end):
    free = []
    cursor = window_start

    for busy_start, busy_end in busy:
        if busy_start >= window_end:
            break

        start = max(busy_start, window_start)
        end = min(busy_end, window_end)

        if end <= cursor:
            continue
        if start > cursor:
            free.append((cursor, start))

        cursor = max(cursor, end)
        if cursor >= window_end:
            break

    if cursor < window_end:
        free.append((cursor, window_end))

    return [(start, end) for start, end in free if end > start]


@frappe.whitelist()
def get_calendar_events(employee: str, from_date: str, to_date: str, work_start: str = "08:00", work_end: str = "18:00"):
    """Return busy and free slots for a date range from CalDAV data."""
    import pytz

    if not employee:
        frappe.throw("Employee is required.")
    if not from_date or not to_date:
        frappe.throw("From Date and To Date are required.")

    start_day = getdate(from_date)
    end_day = getdate(to_date)
    if start_day > end_day:
        frappe.throw("From Date cannot be after To Date.")

    user_id = _resolve_calendar_user(employee)
    tz = pytz.timezone(frappe.db.get_value("User", user_id, "time_zone") or get_site_timezone())

    range_start_utc, _ = _day_bounds_utc(start_day, tz)
    _, range_end_utc = _day_bounds_utc(end_day, tz)

    busy_intervals = fetch_busy_intervals_from_sogo(
        user_id,
        range_start_utc,
        range_end_utc,
        merge_overlaps=False,
        include_all_calendars=True,
    )

    busy_intervals = [
        (max(start, range_start_utc), min(end, range_end_utc))
        for start, end in busy_intervals
        if end > range_start_utc and start < range_end_utc
    ]

    busy_events = [
        {
            "start": _to_local_calendar_iso(start, tz),
            "end": _to_local_calendar_iso(end, tz),
            "status": "busy",
        }
        for start, end in busy_intervals
    ]

    free_events = []
    day = start_day
    while day <= end_day:
        window_start, window_end = _work_window_for_day(day, tz, work_start, work_end)
        free_intervals = _subtract_busy_from_window(busy_intervals, window_start, window_end)
        free_events.extend(
            {
                "start": _to_local_calendar_iso(start, tz),
                "end": _to_local_calendar_iso(end, tz),
                "status": "free",
            }
            for start, end in free_intervals
        )
        day += timedelta(days=1)

    return {"events": free_events + busy_events}
