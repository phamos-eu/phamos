"""A weekly repeat starts on its first ticked weekday (#1949, #1991).

The invite of a weekly repeat carries the start as DTSTART and the ticked weekdays as BYDAY. A start
on a weekday that isn't ticked makes calendars show an extra first appointment on that day, while
Frappe's own calendar and the cockpit don't. So on save the start moves forward to the first ticked
weekday, the end with it. One rule for the General Management Cockpit (general_management_spa), the
Events table on Team and Department (team_daily_schedule.validate_schedule_rows) and Frappe Event
(validate_event). spa_shared/utils/appointments.js mirrors it as firstWeeklyStart for the dialog hint.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, formatdate, get_datetime, getdate

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def first_weekly_start(values, start, end):
	"""Start and end of the first appointment of `values`' repeat, as datetimes (no end stays None).

	A weekly repeat whose start is on a weekday that isn't ticked moves forward to the first ticked
	one, the end by the same number of days. No ticked weekday: the repeat runs on the start's own
	weekday, nothing moves. Other repeats and no repeat: nothing moves.
	"""
	start = get_datetime(start)
	end = get_datetime(end) if end else None
	ticked = [index for index, day in enumerate(WEEKDAYS) if cint(values.get(day))]
	weekly = cint(values.get("repeat_this_event")) and values.get("repeat_on") == "Weekly"
	if not (weekly and ticked and start):
		return start, end
	days_ahead = min((index - start.weekday()) % 7 for index in ticked)
	return add_days(start, days_ahead), add_days(end, days_ahead) if end else None


def move_to_first_weekly_day(doc, start_field, end_field, row_number=None):
	"""Move doc's start and end to its first ticked weekday, with a message. Returns the new start,
	or None when nothing moved. Callers run it only when the invite is sent again, so an old row
	doesn't move (and mail its attendees) on an unrelated save (#1814).
	row_number: names the row of an Events table in the messages.
	"""
	if not doc.get(start_field):
		return None
	start, end = first_weekly_start(doc, doc.get(start_field), doc.get(end_field))
	if start == get_datetime(doc.get(start_field)):
		return None
	if doc.get("repeat_till") and getdate(doc.get("repeat_till")) < start.date():
		if row_number:
			frappe.throw(
				_("Row #{0}: the first appointment would be on {1}, after Repeat until").format(
					row_number, formatdate(start)
				)
			)
		frappe.throw(_("The first appointment would be on {0}, after Repeat until").format(formatdate(start)))
	doc.set(start_field, start)
	doc.set(end_field, end)
	if row_number:
		message = _("Row #{0}: the first appointment is on {1}. Start and end were moved to that day.").format(
			row_number, formatdate(start)
		)
	else:
		message = _("The first appointment is on {0}. Start and end were moved to that day.").format(
			formatdate(start)
		)
	frappe.msgprint(message, title=_("Weekly repeat"), indicator="blue")
	return start


def validate_event(doc, method=None):
	"""Event validate hook: a weekly Event starts on its first ticked weekday (#1991). Every save
	sends the Event's invite again (sync_event.on_upsert), so it applies on every save."""
	move_to_first_weekly_day(doc, "starts_on", "ends_on")
