import frappe
from frappe.model.document import Document
from frappe.utils import nowdate
from datetime import date, timedelta


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
    day_name = work_date.strftime("%A")

    weekly_working_hours = frappe.db.get_value(
        "Weekly Working Hours",
        {"employee": employee},
        "name"
    )

    if not weekly_working_hours:
        return 0

    hours = frappe.db.get_value(
        "Daily Hours Detail",
        {
            "parent": weekly_working_hours,
            "day": day_name
        },
        "hours"
    )

    return hours or 0


def get_week_bounds(for_date):
    """Return (week_start, week_end) for the ISO week containing for_date."""
    week_start = for_date - timedelta(days=for_date.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start, week_end

def update_all_teams_weekly_holidays():
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
                    "from_date": ["<=", month_end],
                    "to_date": [">=", month_start],
                },
                fields=["from_date", "to_date", "leave_type", "half_day"]
            )

            for leave in leave_apps:
                day = max(leave.from_date, month_start)
                last_day = min(leave.to_date, month_end)

                while day <= last_day:
                    if day not in employee_holiday_dates:
                        hours = get_employee_working_hours(employee, day)
                        if leave.half_day:
                            hours = hours / 2

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


        current_week_leave_hrs = sum(
            (x.hrs or 0)
            for x in doc.team_member_leaves_and_holiday
            if x.date == today 
        )

        doc.total_team_capacity = team_members_capacity - current_week_leave_hrs

        doc.save(ignore_permissions=True)

        # Upsert today's ledger entry
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

    frappe.db.commit()