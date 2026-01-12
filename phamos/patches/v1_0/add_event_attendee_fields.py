"""
Add custom fields to Event doctype for storing attendees from hybrid meeting composer
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    """Add custom attendee fields to Event doctype"""
    
    custom_fields = {
        "Event": [
            {
                "fieldname": "custom_attendees_to",
                "label": "Attendees (To)",
                "fieldtype": "Small Text",
                "insert_after": "event_participants",
                "description": "Required attendees (comma-separated emails)",
                "hidden": 1,
            },
            {
                "fieldname": "custom_attendees_cc",
                "label": "Attendees (CC)",
                "fieldtype": "Small Text",
                "insert_after": "custom_attendees_to",
                "description": "Optional attendees - CC (comma-separated emails)",
                "hidden": 1,
            },
            {
                "fieldname": "custom_attendees_bcc",
                "label": "Attendees (BCC)",
                "fieldtype": "Small Text",
                "insert_after": "custom_attendees_cc",
                "description": "Optional attendees - BCC (comma-separated emails)",
                "hidden": 1,
            },
        ]
    }
    
    create_custom_fields(custom_fields, update=True)
    frappe.db.commit()
    
    print("✓ Added custom attendee fields to Event doctype")
