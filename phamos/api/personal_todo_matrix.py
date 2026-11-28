# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Eisenhower matrix of my open ToDos for the Personal Cockpit (phamos/phamos#1555).

Importance is the user's own judgement (`cockpit_important`, seeded from priority High);
urgency follows from the due date: due within URGENT_WORKING_DAYS working days, or overdue.
Moving a ToDo between quadrants therefore sets the flag and, where urgency changes, the date.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, getdate, today

from phamos.api import personal_todos
from phamos.cockpits.defaults import MATRIX_LIMIT, URGENT_WORKING_DAYS
from phamos.cockpits.workdays import add_working_days

# Quadrant keys in the order the matrix shows them (row by row).
QUADRANTS = {
	"do": {"important": True, "urgent": True},
	"schedule": {"important": True, "urgent": False},
	"delegate": {"important": False, "urgent": True},
	"eliminate": {"important": False, "urgent": False},
}
SCOPES = ("week", "all")
PAYOFF_PREFIX = "Why it matters"


def urgent_until(on=None):
	"""Last due date that still counts as urgent."""
	return add_working_days(on or today(), URGENT_WORKING_DAYS)


def end_of_week(on=None):
	on = getdate(on or today())
	return on + timedelta(days=6 - on.weekday())


def is_urgent(date, horizon):
	return bool(date) and getdate(date) <= getdate(horizon)


def quadrant_of(todo, horizon):
	important = bool(todo.get("important"))
	urgent = is_urgent(todo.get("date"), horizon)
	for key, rule in QUADRANTS.items():
		if rule["important"] == important and rule["urgent"] == urgent:
			return key


def in_scope(todo, scope, week_end):
	"""This week: due by Sunday, undated, or important (the Schedule quadrant lives later)."""
	if scope == "all":
		return True
	date = todo.get("date")
	return not date or getdate(date) <= week_end or todo.get("important")


def get_matrix(scope="week"):
	if scope not in SCOPES:
		frappe.throw(_("Unknown scope: {0}").format(scope))
	horizon = urgent_until()
	week_end = end_of_week()
	quadrants = {key: {"items": [], "total": 0} for key in QUADRANTS}
	hidden = 0
	for todo in personal_todos.get_my_todos():
		if not in_scope(todo, scope, week_end):
			hidden += 1
			continue
		bucket = quadrants[quadrant_of(todo, horizon)]
		bucket["total"] += 1
		if len(bucket["items"]) < MATRIX_LIMIT:
			bucket["items"].append(todo)
	return {
		"scope": scope,
		"today": getdate(today()),
		"urgent_until": horizon,
		"next_after_urgent": add_working_days(horizon, 1),
		"limit": MATRIX_LIMIT,
		"quadrants": quadrants,
		"out_of_scope": hidden,
	}


def set_quadrant(name, quadrant, date=None, payoff_note=None):
	"""Move one of my open ToDos into a quadrant.

	Into an urgent quadrant: the due date becomes `date` (default today) unless it is urgent
	already. Out of an urgent quadrant: a new date after the urgent horizon is required, so
	the deadline is never silently removed (moving it later counts as a reschedule).
	A payoff note ("what happens if this isn't done?") is kept as a comment.
	"""
	if quadrant not in QUADRANTS:
		frappe.throw(_("Unknown quadrant: {0}").format(quadrant))
	doc = personal_todos._get_my_todo(name)
	doc.check_permission("write")
	if doc.status != "Open":
		frappe.throw(_("Only open ToDos can be moved."))

	rule = QUADRANTS[quadrant]
	horizon = urgent_until()
	urgent_now = is_urgent(doc.date, horizon)

	if rule["urgent"] and not urgent_now:
		new_date = getdate(date) if date else getdate(today())
		if new_date < getdate(today()) or new_date > horizon:
			frappe.throw(_("An urgent ToDo is due between today and {0}.").format(frappe.format(horizon, "Date")))
		doc.date = new_date
	elif not rule["urgent"] and urgent_now:
		if not date:
			frappe.throw(_("Please pick a new due date after {0}.").format(frappe.format(horizon, "Date")))
		new_date = getdate(date)
		if new_date <= horizon:
			frappe.throw(_("Not urgent means due after {0}.").format(frappe.format(horizon, "Date")))
		doc.date = new_date

	if doc.meta.has_field("cockpit_important"):
		doc.cockpit_important = cint(rule["important"])
	doc.save()

	note = (payoff_note or "").strip()
	if note:
		doc.add_comment("Comment", f"{PAYOFF_PREFIX}: {frappe.utils.escape_html(note[:1000])}")

	todo = personal_todos.get_todo(doc.name)
	todo["quadrant"] = quadrant_of(todo, horizon)
	return todo
