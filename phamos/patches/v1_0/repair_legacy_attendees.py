"""Repair the Attendee rows that came from the old event registration (phamos/phamos#1713, finding #1585).

``migrate_attendee_legacy_data`` already ran on production (v15.117.0). It left:
- rows of submitted legacy ticket orders without ``sales_order`` / ``sales_order_item``, so invoices and
  payments never reached them;
- rows of free events on the column default "Pending" instead of "Not Required";
- duplicate rows (the old form allowed the same email twice per event) and emails that fail validation,
  so these rows cannot be saved;
- registrations "for 3 people" counting as one seat.

Idempotent: a second run changes nothing. Every change is printed per event; run it on a copy of production
first and read the output (draft orders, duplicates, group registrations).
"""

import frappe
from frappe.utils import cint, get_datetime, now_datetime

from phamos.marketing.billing import refresh_payment_status
from phamos.marketing.utils import normalize_email

LEGACY_PO_PREFIX = "Ticket purchase for "


def execute():
	clear_invalid_emails()
	link_submitted_orders()
	set_not_required()
	cancel_duplicates()
	expand_group_registrations()


def _say(message):
	print(f"repair_legacy_attendees: {message}")


def _append_note(notes, line):
	return "\n".join(filter(None, [notes, line]))


def clear_invalid_emails():
	for row in frappe.get_all("Attendee", filters={"email": ["is", "set"]}, fields=["name", "email", "notes"]):
		if normalize_email(row.email, throw=False):
			continue
		frappe.db.set_value("Attendee", row.name, {"email": None,
			"notes": _append_note(row.notes, f"Email from the old form: {row.email}")}, update_modified=False)
		_say(f"{row.name}: invalid email {row.email!r} moved to the notes")


def link_submitted_orders():
	"""Rows of a submitted legacy ticket order get its line; draft orders are only listed (linking them would
	block deleting the draft)."""
	rows = frappe.get_all("Attendee", filters={"order_reference": ["is", "set"], "sales_order": ["in", ["", None]]},
		fields=["name", "email", "order_reference", "creation"], order_by="creation asc")
	by_order = {}
	for row in rows:
		by_order.setdefault(row.order_reference, []).append(row)
	lines = []
	for order, attendees in by_order.items():
		so = frappe.db.get_value("Sales Order", order, ["name", "docstatus", "po_no", "customer"], as_dict=True)
		if not so or not (so.po_no or "").startswith(LEGACY_PO_PREFIX):
			continue
		if so.docstatus != 1:
			if so.docstatus == 0:
				_say(f"draft order {so.name} not linked, attendees: {', '.join(a.name for a in attendees)}")
			continue
		items = frappe.get_all("Sales Order Item", filters={"parent": so.name}, fields=["name", "additional_notes"],
			order_by="idx asc")
		taken = set(frappe.get_all("Attendee", filters={"sales_order_item": ["in", [i.name for i in items] or [""]]},
			pluck="sales_order_item"))
		free = [i for i in items if i.name not in taken]
		unmatched = []
		for att in attendees:
			line = next((i for i in free if _line_email(i) and _line_email(i) == (att.email or "")), None)
			if line:
				free.remove(line)
				_link(att, so, line)
				lines.append(line.name)
			else:
				unmatched.append(att)
		for att, line in zip(unmatched, free):  # by position: the rows of the order in creation order
			_link(att, so, line)
			lines.append(line.name)
	refresh_payment_status(lines)


def _line_email(item):
	notes = (item.additional_notes or "").splitlines()
	return normalize_email(notes[-1], throw=False) if notes else ""


def _link(att, so, line):
	frappe.db.set_value("Attendee", att.name, {"sales_order": so.name, "sales_order_item": line.name,
		"billing_customer": so.customer}, update_modified=False)
	_say(f"{att.name}: linked to {so.name} line {line.name}")


def set_not_required():
	paid_events = set(frappe.get_all("Marketing Content", filters={"ticket_item": ["is", "set"]}, pluck="name"))
	for row in frappe.get_all("Attendee", filters={"payment_status": "Pending", "sales_order": ["in", ["", None]],
			"order_reference": ["in", ["", None]]}, fields=["name", "event"]):
		if row.event not in paid_events:
			frappe.db.set_value("Attendee", row.name, "payment_status", "Not Required", update_modified=False)
			_say(f"{row.name}: free event {row.event}, Not Required")


def cancel_duplicates():
	"""Same event and email twice: keep the row with an order link (sales_order, else order_reference), else the
	oldest; the others are cancelled with a note."""
	rows = frappe.get_all("Attendee", filters={"email": ["is", "set"], "status": ["!=", "Cancelled"]},
		fields=["name", "event", "email", "sales_order", "order_reference", "creation", "notes"],
		order_by="creation asc")
	groups = {}
	for row in rows:
		groups.setdefault((row.event, row.email), []).append(row)
	for (event, email), group in groups.items():
		if len(group) < 2:
			continue
		keep = min(group, key=lambda r: (not r.sales_order, not r.order_reference, r.creation))
		for row in group:
			if row.name == keep.name:
				continue
			frappe.db.set_value("Attendee", row.name, {"status": "Cancelled",
				"notes": _append_note(row.notes, f"Duplicate of {keep.name} (legacy registration)")}, update_modified=False)
			_say(f"{row.name}: duplicate of {keep.name} ({email}, {event}), cancelled")


def expand_group_registrations():
	"""A legacy registration "for N people": placeholder rows for upcoming events (so the seats count), only
	listed for past events."""
	now = now_datetime()
	for row in frappe.get_all("Attendee", filters={"number_of_attendees": [">", 1]},
			fields=["name", "event", "first_name", "last_name", "number_of_attendees", "order_reference",
				"payment_status", "language", "status"]):
		starts_on = frappe.db.get_value("Marketing Content", row.event, "starts_on")
		full_name = " ".join(filter(None, [row.first_name, row.last_name]))
		count = cint(row.number_of_attendees)
		if not starts_on or get_datetime(starts_on) <= now:
			_say(f"{row.name}: past event {row.event}, registration of {full_name} for {count} people, not expanded")
			continue
		for k in range(2, count + 1):
			frappe.get_doc({"doctype": "Attendee", "event": row.event, "first_name": f"Guest {k} of",
				"last_name": full_name, "role": "Guest", "source": "Website", "status": row.status or "Registered",
				"order_reference": row.order_reference, "payment_status": row.payment_status,
				"language": row.language, "crm_status": "Unlinked",
				"notes": f"Created from a legacy registration for {count} people ({row.name})."}).insert(
				ignore_permissions=True)
		frappe.db.set_value("Attendee", row.name, "number_of_attendees", 1, update_modified=False)
		_say(f"{row.name}: {count - 1} placeholder rows added for {full_name} ({row.event})")
