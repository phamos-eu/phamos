import frappe
from frappe.utils import get_datetime

def execute():
    timesheet_records = frappe.get_all(
        "Timesheet Record", 
        filters={"docstatus": 1}, 
        fields=["name", "creation", "to_time"]
    )

    for record in timesheet_records:
        creation = record.creation
        to_time = record.to_time

        if creation and to_time:
            creation_dt = get_datetime(creation)
            to_dt = get_datetime(to_time)

            if creation_dt.date() != to_dt.date():
                color = "Red"
            else:
                duration = (creation_dt - to_dt).total_seconds() / 3600
                if duration < 1:
                    color = "Green"
                else:
                    color = "Amber"

            frappe.db.set_value("Timesheet Record", record.name, "timesheet_record_color", color)

    frappe.db.commit()
