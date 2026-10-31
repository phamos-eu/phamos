# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Focus mode of the Personal Cockpit (phamos/phamos#1556).

The user locks in 1–5 of their open ToDos for a set time (or a stopwatch). While a session
is active the cockpit only shows the focus view; leaving is always possible (the server never
refuses `end_focus`), the friction is in the UI. Time spent on each ToDo is recorded and added
to the ToDo's `cockpit_actual_minutes`, which feeds the estimate calibration later.

Sessions are private: every function works on the session user's own records only.
"""

import math

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, get_datetime, now_datetime, today

from phamos.api import personal_todos
from phamos.cockpits.defaults import (
	BREAK_OUT_BASE_SECONDS,
	BREAK_OUT_MAX_SECONDS,
	FOCUS_FREE_EXIT_SECONDS,
	FOCUS_GRACE_MINUTES,
	FOCUS_MAX_MINUTES,
	FOCUS_MAX_TODOS,
	FOCUS_PRESETS,
	STOPWATCH_MAX_MINUTES,
)

DOCTYPE = "Focus Session"
EVENT = "cockpit_focus_changed"
OUTCOMES = ("Completed", "Broke out", "Expired")


# reading


def _active_name(user=None):
	return frappe.db.get_value(DOCTYPE, {"user": user or frappe.session.user, "status": "Active"}, "name")


def _session_end_limit(doc):
	"""When an active session counts as abandoned."""
	if cint(doc.planned_minutes):
		return add_to_date(get_datetime(doc.planned_end), minutes=FOCUS_GRACE_MINUTES)
	return add_to_date(get_datetime(doc.started_at), minutes=STOPWATCH_MAX_MINUTES)


def break_outs_today(user=None):
	return frappe.db.count(
		DOCTYPE,
		{
			"user": user or frappe.session.user,
			"outcome": "Broke out",
			"ended_at": (">=", get_datetime(today())),
		},
	)


def break_out_wait_seconds(count):
	"""Seconds the break-out button waits after the free first minute: 10, 20, 40, … 160."""
	return min(BREAK_OUT_BASE_SECONDS * 2 ** max(cint(count), 0), BREAK_OUT_MAX_SECONDS)


def _serialize(doc):
	now = now_datetime()
	items = []
	for row in doc.items:
		minutes = cint(row.actual_minutes)
		if row.started_at:
			minutes += _minutes_between(row.started_at, now)
		items.append(
			{
				"todo": row.todo,
				"summary": row.summary,
				"done": bool(row.done),
				"parked": bool(row.parked),
				"resume_note": row.resume_note or "",
				"minutes": minutes,
				"current": row.todo == doc.current_todo,
			}
		)
	breaks = break_outs_today(doc.user)
	return {
		"name": doc.name,
		"status": doc.status,
		"outcome": doc.outcome,
		"started_at": doc.started_at,
		"planned_minutes": cint(doc.planned_minutes),
		"planned_end": doc.planned_end,
		"ended_at": doc.ended_at,
		"server_now": now,
		"current_todo": doc.current_todo,
		"items": items,
		"done_count": sum(1 for item in items if item["done"]),
		"break_outs_today": breaks,
		"free_exit_seconds": FOCUS_FREE_EXIT_SECONDS,
		"break_out_wait_seconds": break_out_wait_seconds(breaks),
	}


def _minutes_between(start, end):
	seconds = (get_datetime(end) - get_datetime(start)).total_seconds()
	return max(0, math.ceil(seconds / 60)) if seconds > 30 else 0


def get_active_focus():
	"""My active session (ended first if it ran past its limit), or None."""
	name = _active_name()
	if not name:
		return None
	doc = frappe.get_doc(DOCTYPE, name)
	if now_datetime() > _session_end_limit(doc):
		_end(doc, "Expired")
		return None
	return _serialize(doc)


def get_focus_session(name):
	doc = _get_my_session(name)
	return _serialize(doc)


def get_focus_options():
	"""Defaults and limits for the start dialog."""
	return {
		"presets": list(FOCUS_PRESETS),
		"max_minutes": FOCUS_MAX_MINUTES,
		"max_todos": FOCUS_MAX_TODOS,
		"break_outs_today": break_outs_today(),
	}


# writing


def _get_my_session(name):
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.user != frappe.session.user:
		frappe.throw(_("This focus session is not yours."), frappe.PermissionError)
	return doc


def _get_my_active():
	name = _active_name()
	if not name:
		frappe.throw(_("There is no active focus session."))
	return frappe.get_doc(DOCTYPE, name)


def _row(doc, todo):
	for row in doc.items:
		if row.todo == todo:
			return row
	frappe.throw(_("This ToDo is not part of the focus session."))


def _stop_clock(doc, row, at=None):
	"""Book the time since the row became current onto the row and its ToDo."""
	if not row.started_at:
		return
	minutes = _minutes_between(row.started_at, at or now_datetime())
	row.actual_minutes = cint(row.actual_minutes) + minutes
	row.started_at = None
	if minutes and frappe.get_meta("ToDo").has_field("cockpit_actual_minutes"):
		current = cint(frappe.db.get_value("ToDo", row.todo, "cockpit_actual_minutes"))
		frappe.db.set_value("ToDo", row.todo, "cockpit_actual_minutes", current + minutes, update_modified=False)


def _make_current(doc, todo):
	now = now_datetime()
	for row in doc.items:
		if row.todo != todo and row.started_at:
			_stop_clock(doc, row, now)
	doc.current_todo = todo
	if todo:
		row = _row(doc, todo)
		row.parked = 0
		if not row.started_at:
			row.started_at = now


def _next_open(doc, after=None):
	"""The next ToDo that is neither done nor parked, in queue order, starting after `after`."""
	rows = list(doc.items)
	start = next((i + 1 for i, row in enumerate(rows) if row.todo == after), 0)
	for row in rows[start:] + rows[:start]:
		if not row.done and not row.parked and row.todo != after:
			return row.todo
	return None


def _publish(doc):
	frappe.publish_realtime(EVENT, {"name": doc.name, "status": doc.status}, user=doc.user, after_commit=True)


def _save(doc):
	doc.flags.ignore_permissions = True
	doc.save()
	_publish(doc)
	return _serialize(doc)


def _end(doc, outcome, reason=None):
	now = now_datetime()
	for row in doc.items:
		_stop_clock(doc, row, now)
	doc.status = "Ended"
	doc.outcome = outcome
	doc.ended_at = now
	doc.current_todo = None
	if reason:
		doc.break_out_reason = reason[:1000]
	return _save(doc)


def start_focus(todos, minutes=FOCUS_PRESETS[0]):
	"""Start a session with my open ToDos, in the given order; the first one is current."""
	if isinstance(todos, str):
		todos = frappe.parse_json(todos)
	todos = list(dict.fromkeys(todos or []))
	if not todos:
		frappe.throw(_("Pick at least one ToDo."))
	if len(todos) > FOCUS_MAX_TODOS:
		frappe.throw(_("A focus session holds at most {0} ToDos.").format(FOCUS_MAX_TODOS))
	minutes = cint(minutes)
	if minutes < 0 or minutes > FOCUS_MAX_MINUTES or 0 < minutes < 5:
		frappe.throw(_("A focus session lasts 5 to {0} minutes, or runs as a stopwatch.").format(FOCUS_MAX_MINUTES))

	active = get_active_focus()
	if active:
		frappe.throw(_("A focus session is already running."))

	rows = []
	for name in todos:
		todo = personal_todos._get_my_todo(name)
		if todo.status != "Open":
			frappe.throw(_("Only open ToDos can be focused on."))
		rows.append({"todo": todo.name, "summary": personal_todos._summary(todo.description)[:140]})

	now = now_datetime()
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"user": frappe.session.user,
			"status": "Active",
			"started_at": now,
			"planned_minutes": minutes,
			"planned_end": add_to_date(now, minutes=minutes) if minutes else None,
			"items": rows,
		}
	)
	_make_current(doc, rows[0]["todo"])
	doc.insert(ignore_permissions=True)
	_publish(doc)
	return _serialize(doc)


def focus_switch(todo):
	doc = _get_my_active()
	row = _row(doc, todo)
	if row.done:
		frappe.throw(_("This ToDo is already done."))
	_make_current(doc, todo)
	return _save(doc)


def focus_mark_done(todo):
	"""Close the ToDo, then continue with the next one; the session completes after the last."""
	doc = _get_my_active()
	row = _row(doc, todo)
	personal_todos.set_status(todo, "Closed")
	_stop_clock(doc, row)
	row.done = 1
	row.done_at = now_datetime()
	row.parked = 0
	if doc.current_todo == todo or not doc.current_todo:
		following = _next_open(doc, after=todo)
		if following:
			_make_current(doc, following)
		elif all(r.done or r.parked for r in doc.items):
			doc.current_todo = None
			if all(r.done for r in doc.items):
				return _end(doc, "Completed")
	return _save(doc)


def focus_park(todo, resume_note=None):
	"""Set a ToDo aside with a note on where to pick it up (also kept on the ToDo)."""
	doc = _get_my_active()
	row = _row(doc, todo)
	if row.done:
		frappe.throw(_("This ToDo is already done."))
	_save_resume_note(row, resume_note)
	_stop_clock(doc, row)
	row.parked = 1
	if doc.current_todo == todo:
		_make_current(doc, _next_open(doc, after=todo))
	return _save(doc)


def _save_resume_note(row, resume_note):
	note = (resume_note or "").strip()[:1000]
	if not note:
		return
	row.resume_note = note
	if frappe.get_meta("ToDo").has_field("cockpit_resume_note"):
		frappe.db.set_value("ToDo", row.todo, "cockpit_resume_note", note, update_modified=False)


def end_focus(outcome="Broke out", reason=None, resume_note=None):
	"""End my active session. Never refused: leaving is the user's right; the UI adds friction."""
	if outcome not in OUTCOMES:
		frappe.throw(_("Unknown outcome: {0}").format(outcome))
	name = _active_name()
	if not name:
		return None
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.current_todo:
		_save_resume_note(_row(doc, doc.current_todo), resume_note)
	return _end(doc, outcome, (reason or "").strip())


def expire_focus_sessions():
	"""Scheduler (every 5 minutes): end sessions that ran past their limit."""
	for name in frappe.get_all(DOCTYPE, filters={"status": "Active"}, pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		if now_datetime() > _session_end_limit(doc):
			_end(doc, "Expired")
	frappe.db.commit()


def get_focus_history(limit=10):
	"""My last sessions, newest first, for the focus page."""
	rows = frappe.get_all(
		DOCTYPE,
		filters={"user": frappe.session.user, "status": "Ended"},
		fields=["name", "outcome", "started_at", "ended_at", "planned_minutes"],
		order_by="started_at desc",
		limit=cint(limit) or 10,
	)
	for row in rows:
		row["done"] = frappe.db.count("Focus Session Item", {"parent": row["name"], "done": 1})
		row["total"] = frappe.db.count("Focus Session Item", {"parent": row["name"]})
	return rows

