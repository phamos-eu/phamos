# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The event schedule table ("Team Daily Schedule" rows) on doctypes other than Team.

Called from after_migrate. Idempotent. The rows sync to Mailcow through the doc_events in hooks.py
(phamos.events.team_daily_schedule), which work on any doctype that has the field ``event_schedule``.

Department holds them (#1949): the General Management Department's rows are the company-wide
appointments of the General Management Cockpit. Placement follows the convention in
phamos/cockpits/setup.py: the section "Implementation Specific" at the very top. Department starts
with a plain field, so an unlabelled Section Break closes the section and no standard field is
swallowed (as in phamos/marketing/setup.py).

Company had an "Events" tab with the same table (#1814). It was removed in #1949; the patch
phamos.patches.v1_0.move_company_events_to_department moves its rows to the General Management
Department and deletes the Company fields.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Phamos"

EVENT_SCHEDULE_FIELDS = {
	"Department": [
		{
			"fieldname": "custom_implementation_specific",
			"label": "Implementation Specific",
			"fieldtype": "Section Break",
			"insert_after": "",
			"collapsible": 0,
			"module": MODULE,
		},
		{
			"fieldname": "event_schedule",
			"label": "Event Schedule",
			"fieldtype": "Table",
			"options": "Team Daily Schedule",
			"insert_after": "custom_implementation_specific",
			"module": MODULE,
			"description": "Events of this department; for the General Management Department the company-wide "
			"appointments of the General Management Cockpit. Each row is sent as an invite from its Email "
			"Account's Mailcow calendar.",
		},
		{
			"fieldname": "custom_implementation_specific_end",
			"fieldtype": "Section Break",
			"insert_after": "event_schedule",
			"module": MODULE,
		},
	],
}


def ensure_event_schedule_fields():
	create_custom_fields(EVENT_SCHEDULE_FIELDS, update=True)
