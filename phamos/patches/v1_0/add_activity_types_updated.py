import frappe

def execute():
    frappe.db.set_value("Activity Type", {"disabled": 0}, "disabled", 1, update_modified=False)

    activity_types = [
        {
            "activity_type": "Working alone",
            "custom_description": "Software Development, Working on Issues, Documentation, Internal Activities (like HR, Sales, Accounting etc.)"
        },
        {
            "activity_type": "Working with Team",
            "custom_description": "Aligning on tasks, internal meetings on and off tasks."
        },
        {
            "activity_type": "Working with Customer",
            "custom_description": "Consulting in Weekly Meetings, Sales calls, on-site meetings of all kinds, discussing requirement"
        }
    ]

    for atype in activity_types:
        if frappe.db.exists("Activity Type", atype["activity_type"]):
            frappe.db.set_value("Activity Type", atype["activity_type"], {
                "custom_description": atype["custom_description"],
                "disabled": 0
            }, update_modified=False)
        else:
            doc = frappe.get_doc({
                "doctype": "Activity Type",
                "activity_type": atype["activity_type"],
                "custom_description": atype["custom_description"],
                "disabled": 0
            })
            doc.insert(ignore_permissions=True)
