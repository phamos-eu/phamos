# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The event schedule table ("Team Daily Schedule" rows) on doctypes other than Team.

Called from after_migrate. Idempotent. The rows sync to Mailcow through the doc_events in hooks.py
(phamos.events.team_daily_schedule), which work on any doctype that has the field ``event_schedule``.

Placement: an "Events" tab like on Team, not the usual top section "Implementation Specific" (see
phamos/cockpits/setup.py). A whole table at the top of Company would push the company details down;
Wolfram agreed to this exception on 2026-11-04.
"""

from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Phamos"

EVENT_SCHEDULE_FIELDS = {
	"Company": [
		{
			"fieldname": "events_tab",
			"label": "Events",
			"fieldtype": "Tab Break",
			# Last field before ERPNext's Dashboard tab, so Events sits just before it.
			"insert_after": "default_operating_cost_account",
			"module": MODULE,
		},
		{
			"fieldname": "event_schedule",
			"label": "Event Schedule",
			"fieldtype": "Table",
			"options": "Team Daily Schedule",
			"insert_after": "events_tab",
			"module": MODULE,
			"description": "Company-wide events. Each row is sent as an invite from its Email Account's Mailcow calendar.",
		},
	],
}


def ensure_event_schedule_fields():
	create_custom_fields(EVENT_SCHEDULE_FIELDS, update=True)
