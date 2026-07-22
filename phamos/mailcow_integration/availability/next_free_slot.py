from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List, Tuple
import frappe
from .caldav_read import fetch_busy_intervals_for_mailbox, fetch_busy_intervals_from_sogo
from ..utils import get_site_timezone

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _round_to_15min(dt: datetime, direction: str = "up") -> datetime:
    """Round datetime to nearest 15-minute interval.
    
    Args:
        dt: datetime to round
        direction: "up" to round up, "down" to round down, "nearest" for nearest
    """
    # Get minutes and seconds
    minutes = dt.minute
    seconds = dt.second
    microseconds = dt.microsecond
    
    # Calculate remainder when divided by 15
    remainder = minutes % 15
    
    if direction == "up":
        # Round up to next 15-minute mark
        if remainder > 0 or seconds > 0 or microseconds > 0:
            add_minutes = 15 - remainder
            return dt.replace(second=0, microsecond=0) + timedelta(minutes=add_minutes)
        else:
            return dt.replace(second=0, microsecond=0)
    elif direction == "down":
        # Round down to previous 15-minute mark
        return dt.replace(second=0, microsecond=0) - timedelta(minutes=remainder)
    else:  # nearest
        # Round to nearest 15-minute mark
        if remainder < 8:
            return dt.replace(second=0, microsecond=0) - timedelta(minutes=remainder)
        else:
            add_minutes = 15 - remainder
            return dt.replace(second=0, microsecond=0) + timedelta(minutes=add_minutes)

def _work_window_utc(day_utc: datetime, start_hhmm="08:00", end_hhmm="18:00", tz_name=None) -> Tuple[datetime, datetime]:
    import pytz
    tz = pytz.timezone(tz_name or get_site_timezone())
    local = day_utc.astimezone(tz)
    sh, sm = map(int, start_hhmm.split(":"))
    eh, em = map(int, end_hhmm.split(":"))
    start_local = tz.localize(datetime(local.year, local.month, local.day, sh, sm, 0).replace(tzinfo=None))
    end_local   = tz.localize(datetime(local.year, local.month, local.day, eh, em, 0).replace(tzinfo=None))
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

def _subtract_busy_from_window(busy: List[Tuple[datetime, datetime]], window: Tuple[datetime, datetime]) -> List[Tuple[datetime, datetime]]:
    free: List[Tuple[datetime, datetime]] = []
    cur = window[0]
    for s, e in busy:
        # clamp to the window
        s = max(s, window[0]); e = min(e, window[1])
        if e <= cur: 
            continue
        if s > cur:
            free.append((cur, s))
        cur = max(cur, e)
        if cur >= window[1]:
            break
    if cur < window[1]:
        free.append((cur, window[1]))
    return [x for x in free if x[1] > x[0]]


def _mailbox_email_from_account(email_account: str | None) -> str | None:
    if not email_account:
        return None
    return frappe.db.get_value("Email Account", email_account, "email_id")


@frappe.whitelist()
def free_slots_for_day(day: str,
                       duration_minutes: int = 60,
                       time_from: str | None = None,
                       time_to: str | None = None,
                       email_account: str | None = None) -> list[dict]:
    """Return up to five free slots for the given date using site/user timezone.

    Args:
        day: 'YYYY-MM-DD'
        duration_minutes: length of each proposed slot
        time_from/time_to: optional HH:MM strings delimiting search window; if missing, full day is used
        email_account: optional Email Account name; when set, busy times are read from that
            functional mailbox calendar instead of the session user's calendar
    """
    import pytz
    from frappe.utils import getdate

    duration = timedelta(minutes=int(duration_minutes))
    # User's timezone if set, otherwise site timezone
    user_tz = frappe.db.get_value("User", frappe.session.user, "time_zone")
    tzname = user_tz or get_site_timezone()
    tz = pytz.timezone(tzname)
    d = getdate(day)
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    is_today_local = (d.year, d.month, d.day) == (now_local.year, now_local.month, now_local.day)

    # Determine local window
    if not time_from:
        time_from = "07:00"
    if not time_to:
        time_to = "18:00"
    sh, sm = map(int, time_from.split(":"))
    eh, em = map(int, time_to.split(":"))
    
    # Round minutes to 15-minute intervals
    sm = (sm // 15) * 15
    em = (em // 15) * 15

    start_local = tz.localize(datetime(d.year, d.month, d.day, sh, sm, 0))
    end_local = tz.localize(datetime(d.year, d.month, d.day, eh, em, 0))
    # Protect against inverted range
    if end_local <= start_local:
        end_local = start_local + timedelta(minutes=int(duration_minutes))

    # Convert to UTC for querying
    day_start_utc = start_local.astimezone(timezone.utc)
    day_end_utc = end_local.astimezone(timezone.utc)

    mailbox_email = _mailbox_email_from_account(email_account)
    if mailbox_email:
        busy = fetch_busy_intervals_for_mailbox(mailbox_email, day_start_utc, day_end_utc)
    else:
        busy = fetch_busy_intervals_from_sogo(frappe.session.user, day_start_utc, day_end_utc)
    free_blocks = _subtract_busy_from_window(busy, (day_start_utc, day_end_utc))

    results: list[dict] = []
    # Offer in 15-minute increments; provide human labels in site/user tz
    for s, e in free_blocks:
        # If looking at today (in user's/site TZ), don't offer past times
        t = max(s, now_utc) if is_today_local else s
        
        # Round start time UP to next 15-minute interval
        t = _round_to_15min(t, direction="up")
        
        while t + duration <= e:
            local_start = t.astimezone(tz)
            local_end = (t + duration).astimezone(tz)
            label = f"{local_start.strftime('%a, %b %d')} — {local_start.strftime('%H:%M')}–{local_end.strftime('%H:%M')}"
            results.append({
                "start": t.isoformat(),
                "end": (t + duration).isoformat(),
                "start_local": local_start.strftime('%Y-%m-%d %H:%M:%S'),
                "end_local": local_end.strftime('%Y-%m-%d %H:%M:%S'),
                "label": label,
            })
            if len(results) >= 5:
                print('\n\n\n RESULTS\n', results, '\n\n\n')
                return results
            t += timedelta(minutes=15)
    print('\n\n\n RESULTS\n', results, '\n\n\n')
    return results

@frappe.whitelist()
def next_three_free_slots_me(duration_minutes: int = 60,
                             search_days: int = 14,
                             work_start: str = "08:00",
                             work_end: str = "18:00",
                             tz_name: str | None = None):
    """
    Look only at the current user's SOGo calendar.
    Return up to 3 soonest slots: [{"start": ISO, "end": ISO}]
    """
    return next_three_free_slots_for_user(
        frappe.session.user,
        duration_minutes=duration_minutes,
        search_days=search_days,
        work_start=work_start,
        work_end=work_end,
        tz_name=tz_name,
    )


def next_three_free_slots_for_user(user_id: str,
                                   duration_minutes: int = 60,
                                   search_days: int = 14,
                                   work_start: str = "08:00",
                                   work_end: str = "18:00",
                                   tz_name: str | None = None):
    """Return the next three free slots from the selected user's SOGo calendar."""
    import pytz

    if not user_id:
        frappe.throw("A calendar user is required to fetch appointment slots.")

    tz_name = (
        tz_name
        or frappe.db.get_value("User", user_id, "time_zone")
        or get_site_timezone()
    )
    tz = pytz.timezone(tz_name)
    now_utc = _now_utc()
    duration = timedelta(minutes=int(duration_minutes))
    results = []

    for day_offset in range(search_days):
        day_start_utc, day_end_utc = _work_window_utc(now_utc + timedelta(days=day_offset),
                                                      work_start, work_end, tz_name)
        busy = fetch_busy_intervals_from_sogo(user_id, day_start_utc, day_end_utc)
        # merge is already done in the fetcher; just subtract
        free_blocks = _subtract_busy_from_window(busy, (day_start_utc, day_end_utc))

        for s, e in free_blocks:
            # don't offer times already passed today
            t = max(s, now_utc) if day_offset == 0 else s
            
            # Round start time UP to next 15-minute interval
            t = _round_to_15min(t, direction="up")
            
            while t + duration <= e:
                local_start = t.astimezone(tz)
                local_end = (t + duration).astimezone(tz)
                results.append({
                    "start": t.isoformat(),
                    "end": (t + duration).isoformat(),
                    "start_local": local_start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_local": local_end.strftime("%Y-%m-%d %H:%M:%S"),
                    "label": (
                        f"{local_start.strftime('%a, %b %d')} — "
                        f"{local_start.strftime('%H:%M')}–{local_end.strftime('%H:%M')}"
                    ),
                })
                if len(results) >= 3:
                    return results
                t += timedelta(minutes=15)

    return results
