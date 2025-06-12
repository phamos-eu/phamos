import frappe

def execute():
    doc = frappe.get_doc("Website Settings")

    existing_labels = {item.label for item in doc.top_bar_items}

    if "Timesheet" not in existing_labels:
        print("updating Website Settings...")
        doc.append("top_bar_items", {
            "label": "Timesheet",
             "url": "/timesheet",
        })
    doc.save()
    frappe.db.commit()
    print("updated Website Settings")

