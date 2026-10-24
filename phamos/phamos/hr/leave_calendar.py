# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Leave Applications as all-day events in the employee's own calendar (milestone 68, Phase 2).

Every Leave Application has at most one Frappe Event (reference_doctype "Leave Application"),
owned by the employee's user and pushed to their SOGo calendar by the regular Event sync
(`mailcow_integration/caldav/sync_event.py`):

- draft: "Leave (draft): <Leave Type>", STATUS TENTATIVE
- submitted and Approved: "Leave: <Leave Type>", STATUS CONFIRMED
- Rejected, Cancelled or deleted: the Event and its calendar object are removed

The Event carries a URL back to the Leave Application, so SOGo and phones show a link.
Saving a Leave Application never waits for SOGo: pushes run after the commit, and a missing
DAV password ends up in `Event.custom_mailcow_sync_error`, shown on the Leave form.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import formatdate, get_url_to_form, getdate

REFERENCE = "Leave Application"
EVENT_COLOR = "#FFC53D"
PUSH_METHOD = "phamos.mailcow_integration.caldav.sync_event.push_event"
DELETE_METHOD = "phamos.mailcow_integration.caldav.sync_event.delete_event_object"
# Event fields this module owns; anything else on the Event is left alone.
MANAGED_FIELDS = (
	"subject",
	"all_day",
	"starts_on",
	"ends_on",
	"event_type",
	"send_reminder",
	"color",
	"reference_doctype",
	"reference_docname",
	"description",
	"custom_mailcow_status",
)


def _employee_user(employee: str | None) -> str | None:
	if not employee:
		return None
	return frappe.db.get_value("Employee", employee, "user_id") or None


def _user_lang(user: str) -> str | None:
	return frappe.db.get_value("User", user, "language") or None


def _desired_state(doc) -> dict | None:
	"""What the calendar should show for this Leave Application, or None for nothing."""
	if doc.docstatus == 2 or doc.status in ("Rejected", "Cancelled"):
		return None
	if doc.docstatus == 1:
		# submitted and not rejected means approved (HRMS only submits Approved or Rejected)
		return {"draft": False, "ical_status": "CONFIRMED"}
	return {"draft": True, "ical_status": "TENTATIVE"}


def _subject(doc, state: dict, lang: str | None) -> str:
	leave_type = _(doc.leave_type, lang=lang) if doc.leave_type else _("Leave", lang=lang)
	if state["draft"]:
		subject = _("Leave (draft): {0}", lang=lang).format(leave_type)
	else:
		subject = _("Leave: {0}", lang=lang).format(leave_type)
	if doc.get("half_day"):
		half = _("half day", lang=lang)
		single_day = getdate(doc.from_date) == getdate(doc.to_date)
		half_date = doc.get("half_day_date") or doc.from_date
		subject += f" ({half})" if single_day else f" ({half} {formatdate(half_date)})"
	return subject


def _description(doc) -> str:
	# Same marker and link block as Team Daily Schedule events, for clients that ignore URL.
	lines = [f"{doc.employee_name or doc.employee} · {doc.leave_type or ''}".strip(" ·")]
	if doc.get("description"):
		lines.append(doc.description)
	lines.append("")
	lines.append("***** Auto Generated *****")
	lines.append(get_url_to_form(REFERENCE, doc.name))
	return "\n".join(lines)


def _event_values(doc, state: dict, lang: str | None) -> dict:
	return {
		"subject": _subject(doc, state, lang),
		"all_day": 1,
		"starts_on": f"{getdate(doc.from_date)} 00:00:00",
		"ends_on": f"{getdate(doc.to_date)} 23:59:59",
		"event_type": "Private",
		"send_reminder": 0,  # Event defaults to 1, which mails the employee on the first day
		"color": EVENT_COLOR,
		"reference_doctype": REFERENCE,
		"reference_docname": doc.name,
		"description": _description(doc),
		"custom_mailcow_status": state["ical_status"],
	}


def _find_event(leave_name: str):
	rows = frappe.get_all(
		"Event",
		filters={"reference_doctype": REFERENCE, "reference_docname": leave_name},
		fields=["name", "owner", "custom_mailcow_uid", "custom_mailcow_synched", "custom_mailcow_sync_error"],
		order_by="creation asc",
	)
	return rows


def _push(event_name: str):
	if frappe.flags.mailcow_sync_now:
		from phamos.mailcow_integration.caldav.sync_event import push_event

		push_event(event_name)
		return
	frappe.enqueue(PUSH_METHOD, queue="short", enqueue_after_commit=True, event_name=event_name)


def _delete_calendar_object(uid: str, owner: str):
	if frappe.flags.mailcow_sync_now:
		from phamos.mailcow_integration.caldav.sync_event import delete_event_object

		delete_event_object(uid=uid, owner=owner)
		return
	frappe.enqueue(DELETE_METHOD, queue="short", enqueue_after_commit=True, uid=uid, owner=owner)


def _delete_events(rows):
	for row in rows:
		# Event on_trash removes the object from the owner's calendar (after the commit).
		frappe.delete_doc("Event", row.name, ignore_permissions=True, force=True)


def _differs(event, values: dict) -> bool:
	for field, value in values.items():
		current = event.get(field)
		if field in ("starts_on", "ends_on"):
			if str(current or "")[:19] != str(value)[:19]:
				return True
		elif (current or "") != (value or "") and str(current) != str(value):
			return True
	return False


def sync_leave_event(doc, method=None):
	"""Leave Application on_update / on_submit / on_cancel: bring the Event in line.

	Idempotent, so every hook can call it: unchanged values and an already synced Event
	cause no save and no push.
	"""
	if not doc.name or not doc.from_date or not doc.to_date:
		return
	rows = _find_event(doc.name)
	user = _employee_user(doc.employee)
	state = _desired_state(doc)
	if not user or state is None:
		_delete_events(rows)
		return
	# keep one Event per Leave Application
	if len(rows) > 1:
		_delete_events(rows[1:])
	values = _event_values(doc, state, _user_lang(user))

	if not rows:
		event = frappe.get_doc({"doctype": "Event", **values})
		event.flags.skip_mailcow_push = True
		event.insert(ignore_permissions=True)
		# Frappe sets owner to the session user (HR or the approver); the sync writes to the
		# owner's calendar, so the employee must own it.
		event.db_set("owner", user, update_modified=False)
		_push(event.name)
		return

	row = rows[0]
	event = frappe.get_doc("Event", row.name)
	owner_changed = row.owner != user
	if owner_changed:
		# The employee changed on a draft: remove the object from the old mailbox and push
		# create-only into the new one.
		_delete_calendar_object(row.custom_mailcow_uid or row.name, row.owner)
		event.db_set(
			{"owner": user, "custom_mailcow_synched": 0, "custom_mailcow_uid": ""}, update_modified=False
		)
		event.reload()

	changed = _differs(event, values)
	if changed:
		event.update(values)
		event.flags.skip_mailcow_push = True
		event.save(ignore_permissions=True)
	synced_cleanly = row.custom_mailcow_synched and not row.custom_mailcow_sync_error
	if changed or owner_changed or not synced_cleanly:
		_push(event.name)


def remove_leave_event(doc, method=None):
	"""Leave Application on_trash: remove its Event, and with it the calendar object."""
	_delete_events(_find_event(doc.name))


@frappe.whitelist()
def get_calendar_state(leave_application: str) -> dict:
	"""Calendar status for the Leave form.

	HR usually cannot read the employee's Private Event, so the form asks the server; access
	follows read permission on the Leave Application.
	"""
	doc = frappe.get_doc(REFERENCE, leave_application)
	doc.check_permission("read")
	user = _employee_user(doc.employee)
	rows = _find_event(doc.name)
	row = rows[0] if rows else None
	if not user:
		reason = "no_user"
	elif not row:
		reason = "no_event"
	elif row.custom_mailcow_sync_error:
		reason = "error"
	elif not row.custom_mailcow_synched:
		reason = "pending"
	else:
		reason = None
	return {
		"event": row.name if row else None,
		"user": user,
		"synced": bool(row and row.custom_mailcow_synched and not row.custom_mailcow_sync_error),
		"error": (row.custom_mailcow_sync_error or "") if row else "",
		"reason": reason,
	}
