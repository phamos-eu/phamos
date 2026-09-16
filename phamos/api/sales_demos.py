# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Demos API — scheduling demos against a Lead."""

import json

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
	"location",
	"owner",
	"modified",
]

DEMO_STATUSES = ("Planned", "Completed", "Cancelled")


@frappe.whitelist()
def get_demos(lead=None):
	"""Return Demos, soonest scheduled first; unscheduled ones last."""
	_check_lead_access()
	frappe.has_permission("Demo", "read", throw=True)

	rows = frappe.get_all(
		"Demo",
		filters={"lead": lead} if lead else None,
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


def _create_demo_event(demo_subject, lead, lead_doc, starts_on, ends_on, agenda, location, participants):
	"""Tentative calendar entry holding one proposed slot.

	Invitees who map to a User become Event Participant rows carrying
	`custom_participation` (which the CalDAV sync turns into REQ/OPT
	attendee roles). Plain email invitees can't: Event Participants
	requires a linked record, so they ride along in the attendee fields,
	required in TO and optional in CC — the same split the hybrid meeting
	composer uses.
	"""
	rows = [{"reference_doctype": "Lead", "reference_docname": lead, "custom_participation": "Required"}]
	required = [lead_doc.email_id] if lead_doc.email_id else []
	optional = []

	for participant in participants:
		email = (participant.get("email") or "").strip()
		if not email:
			continue
		is_required = (participant.get("participation") or "Required") == "Required"
		user = participant.get("user")
		if user and frappe.db.exists("User", user):
			rows.append(
				{
					"reference_doctype": "User",
					"reference_docname": user,
					"email": email,
					"custom_participation": "Required" if is_required else "Optional",
				}
			)
		if email in required or email in optional:
			continue
		(required if is_required else optional).append(email)

	event = frappe.get_doc(
		{
			"doctype": "Event",
			"subject": demo_subject,
			"event_type": "Private",
			"starts_on": starts_on,
			"ends_on": ends_on or None,
			"description": agenda or "",
			"location": location or "",
			"event_participants": rows,
			"custom_attendees_to": ", ".join(required),
			"custom_attendees_cc": ", ".join(optional),
		}
	)
	event.insert()
	return event.name


@frappe.whitelist(methods=["POST"])
def create_demo(lead, subject, slots=None, participants=None, agenda=None, location=None):
	"""Create a Demo for a Lead, holding a calendar Event per proposed slot.

	A demo often isn't pinned to one date yet, so `slots` takes any number
	of `{starts_on, ends_on}` proposals and each gets a tentative Event —
	the same hold-the-slot approach `mailcow_integration.hybrid_meeting`
	takes. A single proposal is treated as already settled and populates
	`scheduled_on`/`event` directly.

	Events are inserted rather than routed through the hybrid-meeting
	composer so that planning a demo never sends mail on its own — the
	Event doc_events hooks still sync them to the organiser's calendar, and
	the Lead is attached as a participant so the integration can resolve
	the customer's address when an invite is sent later.
	"""
	_check_lead_access()
	frappe.has_permission("Demo", "create", throw=True)

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	if isinstance(slots, str):
		slots = json.loads(slots)
	slots = [s for s in (slots or []) if s.get("starts_on")]

	if isinstance(participants, str):
		participants = json.loads(participants)
	participants = participants or []

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	demo = frappe.get_doc(
		{
			"doctype": "Demo",
			"subject": subject,
			"lead": lead,
			"status": "Planned",
			"agenda": agenda or None,
			"location": location or None,
		}
	)
	demo.insert()

	for slot in sorted(slots, key=lambda s: str(s.get("starts_on"))):
		event_name = _create_demo_event(
			subject, lead, lead_doc, slot["starts_on"], slot.get("ends_on"), agenda, location, participants
		)
		demo.append(
			"proposed_slots",
			{"starts_on": slot["starts_on"], "ends_on": slot.get("ends_on"), "event": event_name},
		)

	# One proposal is a decision, not a choice to put to the customer.
	if len(demo.proposed_slots) == 1:
		only = demo.proposed_slots[0]
		demo.scheduled_on = only.starts_on
		demo.ends_on = only.ends_on
		demo.event = only.event

	demo.save()
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
		"location": doc.location,
		"proposed_slots": [
			{
				"name": row.name,
				"starts_on": row.starts_on,
				"ends_on": row.ends_on,
				"event": row.event,
			}
			for row in (doc.get("proposed_slots") or [])
		],
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
