# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Demos API — scheduling demos against a Lead."""

import json
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils.html_utils import clean_email_html

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


def _attendee_event_fields(lead, lead_doc, participants):
	"""Turn a demo's attendees into the three fields an Event needs.

	Invitees who map to a User become Event Participant rows carrying
	`custom_participation` (which the CalDAV sync turns into REQ/OPT
	attendee roles). Plain email invitees can't: Event Participants
	requires a linked record, so they ride along in the attendee fields,
	required in TO and optional in CC — the same split the hybrid meeting
	composer uses.

	Shared by creating a demo and by editing its attendees later, so the two
	paths can't drift apart.
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

	return rows, required, optional


def _create_demo_event(
	demo_subject, lead, lead_doc, starts_on, ends_on, agenda, location, participants, demo=None
):
	"""Tentative calendar entry holding one proposed slot.

	Stamped with `custom_demo` so the cockpit can tell its own holds apart from
	every other event on the site — see `_demo_event_names`.
	"""
	rows, required, optional = _attendee_event_fields(lead, lead_doc, participants)

	event = frappe.get_doc(
		{
			"doctype": "Event",
			"custom_demo": demo,
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
			# Kept on the demo as well as on each slot's event: a demo with
			# three proposed slots has three events, none of which is the
			# record of who was invited.
			"attendees": _attendee_rows(participants),
		}
	)
	demo.insert()

	for slot in sorted(slots, key=lambda s: str(s.get("starts_on"))):
		event_name = _create_demo_event(
			subject,
			lead,
			lead_doc,
			slot["starts_on"],
			slot.get("ends_on"),
			agenda,
			location,
			participants,
			demo=demo.name,
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


def _attendee_rows(participants):
	"""Normalise incoming attendee dicts into Demo Attendee child rows."""
	rows = []
	seen = set()
	for participant in participants or []:
		email = (participant.get("email") or "").strip()
		user = (participant.get("user") or "").strip()
		full_name = (participant.get("full_name") or "").strip()
		key = email.casefold() or user.casefold() or full_name.casefold()
		if not key or key in seen:
			continue
		seen.add(key)
		if not full_name and user:
			# The dialog sends an address, not a name; a User has a real one.
			full_name = _user_label(user)
		rows.append(
			{
				"contact": participant.get("contact") or None,
				"user": user or None,
				"full_name": full_name or (email.split("@")[0] if email else user),
				"email": email or None,
				"participation": participant.get("participation") or "Required",
				# One of ours if they're a User; otherwise assume the customer side.
				"audience": participant.get("audience") or ("Internal" if user else "External"),
				# Blank until someone records it after the demo.
				"attended": participant.get("attended") or None,
			}
		)
	return rows


def _serialize_attendees(doc):
	return [
		{
			"name": row.name,
			"contact": row.contact,
			"user": row.user,
			"full_name": row.full_name,
			"email": row.email,
			"participation": row.participation,
			"audience": row.audience,
			"attended": row.attended,
		}
		for row in (doc.get("attendees") or [])
	]


def _meeting_url(location):
	"""A location that's really a video link, so the UI can offer a Join button.

	The field holds either a street address or a meeting URL — the create
	dialog writes a Jitsi room into it — so this is what decides which.

	Deliberately just a scheme check, not the SSRF guard used for the lead
	website preview: nothing is fetched server-side here, the user clicks the
	link in their own browser, and a self-hosted meeting server on a private
	address is a perfectly good place to hold a demo.
	"""
	value = (location or "").strip()
	if not value or any(c.isspace() for c in value):
		return ""
	parsed = urlparse(value)
	return value if parsed.scheme in ("http", "https") and parsed.hostname else ""


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
		"next_followup": doc.next_followup,
		"meeting_url": _meeting_url(doc.location),
		"nextcloud_link": doc.nextcloud_link,
		"nextcloud_url": _meeting_url(doc.nextcloud_link),
		"attendees": _serialize_attendees(doc),
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
		"feedback_count": frappe.db.count("Demo Feedback", {"demo": doc.name}),
		"desk_url": f"/app/demo/{doc.name}",
	}


@frappe.whitelist()
def get_demo(name):
	"""Return a single Demo for the cockpit."""
	_check_lead_access()
	doc = frappe.get_doc("Demo", name)
	doc.check_permission("read")
	return _serialize_demo(doc)


DEMO_EDITABLE_FIELDS = (
	"subject",
	"status",
	"scheduled_on",
	"ends_on",
	"next_followup",
	"location",
	"nextcloud_link",
	"agenda",
)


@frappe.whitelist(methods=["POST"])
def update_demo(name, if_modified=None, **fields):
	"""Update whitelisted Demo fields, autosave-style.

	`if_modified` is the `modified` timestamp the client last saw; a mismatch
	means someone else saved since, and the edit is refused rather than
	silently overwriting them — the same low-friction contract as
	`sales_leads.update_lead`.
	"""
	_check_lead_access()
	frappe.has_permission("Demo", "write", throw=True)

	doc = frappe.get_doc("Demo", name)
	doc.check_permission("write")

	if if_modified and str(doc.modified) != str(if_modified):
		return {"conflict": True, "demo": _serialize_demo(doc)}

	updates = {k: v for k, v in fields.items() if k in DEMO_EDITABLE_FIELDS}
	if not updates:
		return {"demo": _serialize_demo(doc)}

	if "status" in updates and updates["status"] not in DEMO_STATUSES:
		frappe.throw(_("Unknown demo status: {0}").format(updates["status"]))

	for field, value in updates.items():
		doc.set(field, value if value not in ("", None) else None)

	doc.save()

	if "next_followup" in updates:
		_sync_lead_followup(doc)

	return {"demo": _serialize_demo(frappe.get_doc("Demo", name))}


def _sync_lead_followup(demo):
	"""Push the demo's follow-up date onto its Lead.

	A demo is a step in the lead's pipeline, so agreeing a follow-up here is
	agreeing one there. The lead also keeps a next step labelled after this
	demo — matched on that label so moving the date updates the row rather
	than piling up a new one, the same way the lead's own "Planned start"
	row works.

	Goes through the document rather than db_set so validation, versioning
	and the Desk client's own stamps still fire.
	"""
	if not demo.lead or not frappe.db.exists("Lead", demo.lead):
		return

	lead = frappe.get_doc("Lead", demo.lead)
	# Writing the demo is not a licence to write its lead: without this, anyone
	# who can create a demo against a lead could set that lead's follow-up date
	# and append a next step to it.
	lead.check_permission("write")
	lead.custom_next_followup = demo.next_followup or None

	label = f"Follow up on {demo.name}"
	if demo.next_followup:
		for row in lead.get("custom_next_steps") or []:
			if (row.next_step or "").strip().lower() == label.lower():
				row.date = demo.next_followup
				break
		else:
			lead.append("custom_next_steps", {"next_step": label, "date": demo.next_followup})

	lead.save()


@frappe.whitelist(methods=["POST"])
def set_demo_attendees(name, rows=None):
	"""Replace the attendee list and re-sync it onto the demo's calendar events."""
	_check_lead_access()
	frappe.has_permission("Demo", "write", throw=True)

	doc = frappe.get_doc("Demo", name)
	doc.check_permission("write")

	if isinstance(rows, str):
		rows = json.loads(rows)

	doc.set("attendees", _attendee_rows(rows))
	doc.save()

	_sync_demo_events(doc)
	return _serialize_demo(frappe.get_doc("Demo", name))


def _demo_event_names(doc):
	"""Events this demo actually owns.

	`proposed_slots[].event` is read-only in the form but not on the API: a
	Sales User may write a Demo, so nothing stops a crafted child row naming
	someone else's event. Without this filter, editing attendees would rewrite
	that event's invitee list and confirming a slot would delete it outright.
	Only events stamped with this demo are ever touched.
	"""
	claimed = {row.event for row in (doc.get("proposed_slots") or []) if row.event}
	if doc.event:
		claimed.add(doc.event)
	if not claimed:
		return set()

	return set(
		frappe.get_all(
			"Event",
			filters={"name": ["in", list(claimed)], "custom_demo": doc.name},
			pluck="name",
		)
	)


def _sync_demo_events(doc):
	"""Push the demo's attendees onto every event still holding a slot.

	A demo keeps one tentative event per proposed slot, so a change of
	invitees has to reach all of them, not just the confirmed one.
	"""
	lead_doc = frappe.get_doc("Lead", doc.lead)
	participants = _serialize_attendees(doc)
	rows, required, optional = _attendee_event_fields(doc.lead, lead_doc, participants)

	for event_name in _demo_event_names(doc):
		event = frappe.get_doc("Event", event_name)
		event.set("event_participants", rows)
		event.custom_attendees_to = ", ".join(required)
		event.custom_attendees_cc = ", ".join(optional)
		event.save(ignore_permissions=True)


@frappe.whitelist(methods=["POST"])
def confirm_demo_slot(name, slot):
	"""Settle on one proposed slot and release the others.

	The losing slots' events were only ever holds, so they're deleted rather
	than left cluttering everyone's calendar.
	"""
	_check_lead_access()
	frappe.has_permission("Demo", "write", throw=True)

	doc = frappe.get_doc("Demo", name)
	doc.check_permission("write")

	chosen = next((row for row in (doc.get("proposed_slots") or []) if row.name == slot), None)
	if not chosen:
		frappe.throw(_("That proposed slot is no longer on this demo."))

	# Resolved before the table is rewritten, and only events this demo holds.
	ours = _demo_event_names(doc)

	doc.scheduled_on = chosen.starts_on
	doc.ends_on = chosen.ends_on
	doc.event = chosen.event

	released = [row for row in doc.proposed_slots if row.name != chosen.name]
	doc.set("proposed_slots", [chosen])
	doc.save()

	for row in released:
		if row.event and row.event in ours:
			frappe.delete_doc("Event", row.event, ignore_permissions=True, delete_permanently=True)

	return _serialize_demo(frappe.get_doc("Demo", name))


def _serialize_feedback(doc):
	return {
		"name": doc.name,
		"demo": doc.demo,
		"audience": doc.audience,
		"respondent_name": doc.respondent_name,
		"contact": doc.contact,
		"user": doc.user,
		# Frappe's generic Text Editor sanitising still allows <style>, which in
		# an unscoped v-html would restyle the whole cockpit. The email cleaner
		# is the tighter allowlist, and it is what the mail feed already uses.
		"notes": clean_email_html(doc.notes or ""),
		"modules": [
			{"module": row.module, "module_name": row.module_name or row.module}
			for row in (doc.get("modules") or [])
		],
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"modified": doc.modified,
		"desk_url": f"/app/demo-feedback/{doc.name}",
	}


@frappe.whitelist()
def get_demo_feedback(demo):
	"""Every response collected for a demo, internal and external."""
	_check_lead_access()
	demo_doc = frappe.get_doc("Demo", demo)
	demo_doc.check_permission("read")

	names = frappe.get_all(
		"Demo Feedback", filters={"demo": demo}, order_by="creation asc", pluck="name"
	)
	return [_serialize_feedback(frappe.get_doc("Demo Feedback", name)) for name in names]


@frappe.whitelist(methods=["POST"])
def save_demo_feedback(
	demo,
	respondent_name,
	name=None,
	audience=None,
	contact=None,
	user=None,
	notes=None,
	modules=None,
):
	"""Create or update one respondent's feedback on a demo."""
	_check_lead_access()
	demo_doc = frappe.get_doc("Demo", demo)
	demo_doc.check_permission("read")

	respondent_name = (respondent_name or "").strip()
	if not respondent_name:
		frappe.throw(_("A respondent name is required."))

	if isinstance(modules, str):
		modules = json.loads(modules)

	if name:
		doc = frappe.get_doc("Demo Feedback", name)
		doc.check_permission("write")
		if doc.demo != demo:
			frappe.throw(_("That feedback belongs to another demo."))
	else:
		frappe.has_permission("Demo Feedback", "create", throw=True)
		doc = frappe.new_doc("Demo Feedback")
		doc.demo = demo

	doc.respondent_name = respondent_name
	doc.audience = audience or "Internal"
	doc.contact = contact or None
	doc.user = user or None
	doc.notes = notes or None
	doc.set(
		"modules",
		[{"module": row["module"]} for row in (modules or []) if row.get("module")],
	)
	doc.save()

	return _serialize_feedback(frappe.get_doc("Demo Feedback", doc.name))


@frappe.whitelist(methods=["POST"])
def delete_demo_feedback(name):
	"""Remove one response."""
	_check_lead_access()
	doc = frappe.get_doc("Demo Feedback", name)
	doc.check_permission("delete")
	frappe.delete_doc("Demo Feedback", name)
	return {"ok": True}
