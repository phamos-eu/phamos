import frappe

from frappe import _
from frappe.utils import getdate, get_datetime, cint
from datetime import datetime, timedelta

from phamos.phamos.doctype.employee_availability.employee_availability import DEFAULT_TIME_FROM, DEFAULT_TIME_TO, WORKING_DAYS_PER_WEEK, _build_free_slots_for_range, _exclude_optional_from_slot_rows, _subtract_intervals


@frappe.whitelist()
def get_common_free_slots(
    from_email: str,
    to_email: str,
    from_date: str,
    to_date: str,
    duration: int = 60,
    time_from: str = DEFAULT_TIME_FROM,
    time_to: str = DEFAULT_TIME_TO,
):
    """Find overlapping free slots between two users based on their email addresses."""
    if not from_email or not to_email:
        frappe.throw(_("Both From Email and To Email are required."))
    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required."))

    step_minutes = int(duration or 60)
    if step_minutes <= 0:
        frappe.throw(_("Duration must be greater than 0."))

    # Ensure time strings only contain HH:MM to prevent strptime seconds mismatch
    time_from = (time_from or DEFAULT_TIME_FROM)[:5]
    time_to = (time_to or DEFAULT_TIME_TO)[:5]

    start_date = getdate(from_date)
    end_date = getdate(to_date)
    if start_date > end_date:
        frappe.throw(_("From Date cannot be after To Date."))

    def _resolve_user_by_email(email: str):
        user_id = frappe.db.get_value("User", {"email": email}, "name")
        if not user_id:
            frappe.throw(_("User with email {0} not found in the system.").format(frappe.bold(email)))

        if not frappe.db.exists("Mailcow DAV Password", {"user": email}):
            frappe.throw(
                _("No Mailcow DAV Password found for {0}. Please generate DAV password first.").format(
                    frappe.bold(email)
                )
            )
        return user_id

    user1_id = _resolve_user_by_email(from_email)
    user2_id = _resolve_user_by_email(to_email)

    slots1 = _build_free_slots_for_range(
        user_id=user1_id,
        from_date=start_date,
        to_date=end_date,
        tz_name=None,
        time_from=time_from,
        time_to=time_to,
    )
    slots1 = _exclude_optional_from_slot_rows(slots1)
    slots1 = [s for s in slots1 if s["date"].weekday() < WORKING_DAYS_PER_WEEK]

    slots2 = _build_free_slots_for_range(
        user_id=user2_id,
        from_date=start_date,
        to_date=end_date,
        tz_name=None,
        time_from=time_from,
        time_to=time_to,
    )
    slots2 = _exclude_optional_from_slot_rows(slots2)
    slots2 = [s for s in slots2 if s["date"].weekday() < WORKING_DAYS_PER_WEEK]

    intervals1_by_date = {}
    for s in slots1:
        d_str = s["date"].strftime("%Y-%m-%d") if hasattr(s["date"], "strftime") else str(s["date"])
        dt_start = datetime.strptime(f"{d_str} {s['from_time']}", "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(f"{d_str} {s['to_time']}", "%Y-%m-%d %H:%M:%S")
        intervals1_by_date.setdefault(d_str, []).append((dt_start, dt_end))

    intervals2_by_date = {}
    for s in slots2:
        d_str = s["date"].strftime("%Y-%m-%d") if hasattr(s["date"], "strftime") else str(s["date"])
        dt_start = datetime.strptime(f"{d_str} {s['from_time']}", "%Y-%m-%d %H:%M:%S")
        dt_end = datetime.strptime(f"{d_str} {s['to_time']}", "%Y-%m-%d %H:%M:%S")
        intervals2_by_date.setdefault(d_str, []).append((dt_start, dt_end))

    common_slots = []
    all_dates = set(intervals1_by_date.keys()).intersection(set(intervals2_by_date.keys()))

    for d_str in sorted(all_dates):
        invs1 = intervals1_by_date[d_str]
        invs2 = intervals2_by_date[d_str]

        for i1_start, i1_end in invs1:
            for i2_start, i2_end in invs2:
                latest_start = max(i1_start, i2_start)
                earliest_end = min(i1_end, i2_end)
                if latest_start < earliest_end:
                    curr = latest_start
                    while curr + timedelta(minutes=step_minutes) <= earliest_end:
                        next_curr = curr + timedelta(minutes=step_minutes)
                        common_slots.append(
                            {
                                "date": curr.date().strftime("%Y-%m-%d"),
                                "day": curr.strftime("%A"),
                                "from_time": curr.strftime("%H:%M:%S"),
                                "to_time": next_curr.strftime("%H:%M:%S"),
                                "duration_minutes": step_minutes,
                            }
                        )
                        curr = next_curr

    return {
        "from_email": from_email,
        "to_email": to_email,
        "from_date": start_date.strftime("%Y-%m-%d"),
        "to_date": end_date.strftime("%Y-%m-%d"),
        "duration": step_minutes,
        "common_free_slots": common_slots,
    }