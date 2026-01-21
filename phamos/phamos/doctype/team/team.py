import frappe
from frappe.model.document import Document
from frappe.utils import nowdate
from datetime import date, datetime, timedelta


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


def update_all_teams_weekly_holidays():
    today = date.today()
    teams = frappe.get_all("Team", fields=["name"])

    for t in teams:
        doc = frappe.get_doc("Team", t.name)

        doc.set("team_member_leaves_and_holiday", [])

        # ---------------- EMPLOYEE LOOP ----------------
        for member in doc.team_members:
            employee = member.employee
            if not employee:
                continue

            # HOLIDAYS
            holiday_list = frappe.db.get_value("Employee", employee, "holiday_list")
            if holiday_list:
                holidays = frappe.db.get_all(
                    "Holiday",
                    filters={
                        "parent": holiday_list,
                        "holiday_date": today
                    },
                    fields=["holiday_date", "description"]
                )

                for h in holidays:
                    hours = get_employee_working_hours(employee, h.holiday_date)
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
                    "from_date": ["<=", today],
                    "to_date": [">=", today],
                },
                fields=["from_date", "to_date", "leave_type", "half_day"]
            )

            for leave in leave_apps:
                from_d = leave.from_date
                to_d = leave.to_date

                day = from_d
                while day <= to_d:
                    if day == today:
                        hours = get_employee_working_hours(employee, day)
                        doc.append("team_member_leaves_and_holiday", {
                            "employee": employee,
                            "date": day,
                            "leave_type": leave.leave_type,
                            "hrs": hours
                        })
                    day += timedelta(days=1)

        # ---------------- TEAM LEVEL CALCULATIONS ----------------

        team_members_capacity = sum(
            [m.weekly_capacity or 0 for m in doc.team_members]
        )
        doc.team_members_capacity = team_members_capacity

        total_hrs = sum([x.hrs or 0 for x in doc.team_member_leaves_and_holiday])
        doc.team_members_leaves_and_holidays = total_hrs

        team_members_capacitydaily = get_team_daily_capacity(doc, today)
        doc.team_members_capacitydaily = team_members_capacitydaily

        doc.total_team_capacity_daily = team_members_capacitydaily - total_hrs
        doc.total_team_capacity = team_members_capacity - total_hrs


        doc.save(ignore_permissions=True)

        # DAILY LEDGER ENTRY
        frappe.get_doc({
            "doctype": "Team Capacity Ledger",
            "team": doc.team_name,
            "total_team_capacity": doc.total_team_capacity,
            "total_team_capacity_daily": doc.total_team_capacity_daily,
            "date": nowdate()
        }).insert(ignore_permissions=True)

    frappe.db.commit()
