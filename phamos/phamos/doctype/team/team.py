import frappe
from frappe.model.document import Document
from frappe.utils import nowdate
from datetime import date, datetime, timedelta


class Team(Document):
    pass


def update_all_teams_weekly_holidays():
    today = date.today()
    teams = frappe.get_all("Team", fields=["name"])

    for t in teams:
        doc = frappe.get_doc("Team", t.name)

        doc.set("team_member_leaves_and_holiday", [])

        for member in doc.team_members:
            employee = member.employee

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
                    doc.append("team_member_leaves_and_holiday", {
                        "employee": employee,
                        "date": h.holiday_date,
                        "leave_type": h.description,
                        "hrs": 8
                    })

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
                from_d = datetime.strptime(str(leave.from_date), "%Y-%m-%d").date()
                to_d = datetime.strptime(str(leave.to_date), "%Y-%m-%d").date()

                day = from_d
                while day <= to_d:
                    if day == today: 
                        hours = 4 if leave.half_day else 8
                        doc.append("team_member_leaves_and_holiday", {
                            "employee": employee,
                            "date": day,
                            "leave_type": leave.leave_type,
                            "hrs": hours
                        })
                    day += timedelta(days=1)

        team_members_capacity = sum([m.weekly_capacity or 0 for m in doc.team_members])
        doc.team_members_capacity = team_members_capacity

        #  TOTAL LEAVE + HOLIDAY HOURS ---
        total_hrs = sum([x.hrs for x in doc.team_member_leaves_and_holiday])
        doc.team_members_leaves_and_holidays = total_hrs

        doc.total_team_capacity = team_members_capacity - total_hrs

        doc.save(ignore_permissions=True)

        # DAILY LEDGER ENTRY
        frappe.get_doc({
            "doctype": "Team Capacity Ledger",
            "team": doc.team_name,
            "total_team_capacity": doc.total_team_capacity,
            "date": nowdate()
        }).insert(ignore_permissions=True)

    frappe.db.commit()
