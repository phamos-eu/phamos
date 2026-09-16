# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Demos API — scheduling demos against a Lead."""

import frappe
from frappe import _

from phamos.api.department_cockpit import _user_label
from phamos.api.sales_leads import _check_lead_access

DEMO_LIST_LIMIT = 500

DEMO_LIST_FIELDS = [
	"name",
	"subject",
	"lead",
	"lead_name",
	"status",
	"scheduled_on",
	"ends_on",
	"event",
	"owner",
	"modified",
]

DEMO_STATUSES = ("Planned", "Completed", "Cancelled")


@frappe.whitelist()
def get_demos():
	"""Return Demos, soonest scheduled first; unscheduled ones last."""
	_check_lead_access()
	frappe.has_permission("Demo", "read", throw=True)

	rows = frappe.get_all(
		"Demo",
		fields=DEMO_LIST_FIELDS,
		order_by="scheduled_on is null desc, scheduled_on asc",
		limit_page_length=DEMO_LIST_LIMIT + 1,
	)
	truncated = len(rows) > DEMO_LIST_LIMIT
	rows = rows[:DEMO_LIST_LIMIT]

	owners = list(dict.fromkeys(r.owner for r in rows if r.owner))
	owner_names = {owner: _user_label(owner) for owner in owners}
	for row in rows:
		row["owner_name"] = owner_names.get(row.owner) or row.owner

	return {"items": rows, "truncated": truncated, "statuses": list(DEMO_STATUSES)}


@frappe.whitelist(methods=["POST"])
def create_demo(lead, subject, starts_on=None, ends_on=None, agenda=None, location=None):
	"""Create a Demo for a Lead and, when scheduled, a calendar Event for it.

	The Event is inserted rather than routed through the hybrid-meeting
	composer so that scheduling a demo never sends mail on its own — the
	Event doc_events hooks still sync it to the organiser's calendar, and
	the Lead is attached as an event participant so the integration can
	resolve the customer's address when an invite is sent later.
	"""
	_check_lead_access()
	frappe.has_permission("Demo", "create", throw=True)

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	demo = frappe.get_doc(
		{
			"doctype": "Demo",
			"subject": subject,
			"lead": lead,
			"status": "Planned",
			"scheduled_on": starts_on or None,
			"ends_on": ends_on or None,
			"agenda": agenda or None,
		}
	)
	demo.insert()

	if starts_on:
		event = frappe.get_doc(
			{
				"doctype": "Event",
				"subject": subject,
				"event_type": "Private",
				"starts_on": starts_on,
				"ends_on": ends_on or None,
				"description": agenda or "",
				"location": location or "",
				"event_participants": [
					{"reference_doctype": "Lead", "reference_docname": lead}
				],
				"custom_attendees_to": lead_doc.email_id or "",
			}
		)
		event.insert()
		demo.db_set("event", event.name)

	return _serialize_demo(frappe.get_doc("Demo", demo.name))


def _serialize_demo(doc):
	return {
		"name": doc.name,
		"subject": doc.subject,
		"lead": doc.lead,
		"lead_name": doc.lead_name,
		"status": doc.status,
		"scheduled_on": doc.scheduled_on,
		"ends_on": doc.ends_on,
		"event": doc.event,
		"agenda": doc.agenda,
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"desk_url": f"/app/demo/{doc.name}",
	}


@frappe.whitelist()
def get_demo(name):
	"""Return a single Demo for the cockpit."""
	_check_lead_access()
	doc = frappe.get_doc("Demo", name)
	doc.check_permission("read")
	return _serialize_demo(doc)
