import frappe
from frappe.model.document import Document
from frappe.utils import nowdate
from datetime import date, timedelta

from phamos.phamos.team_capacity_utils import (
    LEAVE_FIELDS,
    get_employee_daily_hours,
    get_period_leave_hours,
    leave_day_share,
)


class Team(Document):
    pass


def get_team_daily_capacity(doc, work_date):
    total_daily_hours = 0

    for member in doc.team_members:
        if not member.employee:
            continue

        hours = get_employee_working_hours(member.employee, work_date)
        total_daily_hours += hours

    return total_daily_hours


def get_employee_working_hours(employee, work_date):
    """Scheduled hours of the day, from the Weekly Working Hours valid on it (#1983)."""
    return get_employee_daily_hours(employee, work_date)


def get_week_bounds(for_date):
    """Return (week_start, week_end) for the ISO week containing for_date."""
    week_start = for_date - timedelta(days=for_date.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

def update_all_teams_weekly_holidays():
    # Lead, co-lead and members follow the Team Assignments open today (#1974); first, so the
    # capacity below counts today's members.
    from phamos.phamos.doctype.team_assignment.team_assignment import sync_all_teams

    sync_all_teams()

    today = date.today()

    # Current month date range
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = date(today.year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(today.year, today.month + 1, 1) - timedelta(days=1)

    # Current ISO week bounds
    week_start, week_end = get_week_bounds(today)

    teams = frappe.get_all("Team", fields=["name"])

    for t in teams:
        doc = frappe.get_doc("Team", t.name)
        refresh_team_capacity(doc, today, month_start, month_end, week_start, week_end)
        doc.save(ignore_permissions=True)
        _upsert_ledger_entry(doc)

    frappe.db.commit()


def refresh_team_capacity(doc, today, month_start, month_end, week_start, week_end):
    """Fill the Team's leave and holiday rows for the month and its capacity figures, without saving."""
    doc.set("team_member_leaves_and_holiday", [])

    # ---------------- EMPLOYEE LOOP ----------------
    for member in doc.team_members:
        employee = member.employee
        if not employee:
            continue

        # Track holiday dates to avoid double counting
        employee_holiday_dates = set()

        # Holidays for current month
        holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
        if holiday_list:
            holidays = frappe.db.get_all(
                "Holiday",
                filters={
                    "parent": holiday_list,
                    "holiday_date": ["between", [month_start, month_end]]
                },
                fields=["holiday_date", "description"]
            )

            for h in holidays:
                hours = get_employee_working_hours(employee, h.holiday_date)
                employee_holiday_dates.add(h.holiday_date)

                doc.append("team_member_leaves_and_holiday", {
                    "employee": employee,
                    "date": h.holiday_date,
                    "leave_type": h.description,
                    "hrs": hours
                })

        # LEAVES
        leave_apps = frappe.db.get_all(
            "Leave Application",
            filters={
                "employee": employee,
                "docstatus": 1,
                "status": "Approved",
                "from_date": ["<=", month_end],
                "to_date": [">=", month_start],
            },
            fields=LEAVE_FIELDS
        )

        for leave in leave_apps:
            day = max(leave.from_date, month_start)
            last_day = min(leave.to_date, month_end)

            while day <= last_day:
                if day not in employee_holiday_dates:
                    hours = get_employee_working_hours(employee, day) * leave_day_share(leave, day)

                    doc.append("team_member_leaves_and_holiday", {
                        "employee": employee,
                        "date": day,
                        "leave_type": leave.leave_type,
                        "hrs": hours
                    })
                day += timedelta(days=1)

    # Weekly capacity = sum of all members' weekly capacities
    team_members_capacity = sum(
        [m.weekly_capacity or 0 for m in doc.team_members]
    )
    doc.team_members_capacity = team_members_capacity

    # Total leave/holiday hours for full current month
    total_hrs = sum(
        [x.hrs or 0 for x in doc.team_member_leaves_and_holiday]
    )
    doc.team_members_leaves_and_holidays = total_hrs

    # Daily capacity for today
    team_members_capacitydaily = get_team_daily_capacity(doc, today)
    doc.team_members_capacitydaily = team_members_capacitydaily

    # Todays deductions (leave + holiday)
    today_leave_hrs = sum(
        (x.hrs or 0)
        for x in doc.team_member_leaves_and_holiday
        if x.date == today
    )

    doc.total_team_capacity_daily = team_members_capacitydaily - today_leave_hrs


    # Leave and holidays of the whole current week (#1983: it used to take only today's). Not
    # from the month's rows above: the week can reach into the previous or next month.
    current_week_leave_hrs = sum(
        get_period_leave_hours(m.employee, week_start, week_end)
        for m in doc.team_members
        if m.employee
    )

    doc.total_team_capacity = team_members_capacity - current_week_leave_hrs


def _upsert_ledger_entry(doc):
    """Today's Team Capacity Ledger row of the team, created or updated."""
    today_str = nowdate()
    existing_ledger = frappe.db.get_value(
        "Team Capacity Ledger",
        {"team": doc.name, "date": today_str},
        "name"
    )

    if existing_ledger:
        frappe.db.set_value(
            "Team Capacity Ledger",
            existing_ledger,
            {
                "total_team_capacity": doc.total_team_capacity,
                "total_team_capacity_daily": doc.total_team_capacity_daily,
            },
            update_modified=False
        )
    else:
        frappe.get_doc({
            "doctype": "Team Capacity Ledger",
            "team": doc.name,
            "total_team_capacity": doc.total_team_capacity,
            "total_team_capacity_daily": doc.total_team_capacity_daily,
            "date": today_str
        }).insert(ignore_permissions=True)