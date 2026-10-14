# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Day in the Personal Cockpit (phamos/phamos#1559): plan few, start the day, shut it down.

A Day Plan holds the few ToDos the user means to do on one day. It is a commitment separate
from the due date. "Start the day" fixes the plan; whatever is added later counts as
spontaneous (#1561). Without a start the plan is fixed at FREEZE_HOUR. "Shut down" asks for a
decision on every open item: tomorrow, later this week, a date, drop, or keep it open. Nothing
rolls over silently; unfinished items reappear the next morning as leftovers with a counter.

Plans are private: every function works on the session user's own records only.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, today

from phamos.api import personal_todos
from phamos.cockpits.defaults import (
	CALIBRATION_DAYS,
	CALIBRATION_MIN_SAMPLES,
	CAPACITY_MINUTES,
	DEFAULT_ESTIMATE_MINUTES,
	MY_DAY_CAP,
	ROLLOVER_DECIDE,
)
from phamos.cockpits.workdays import add_working_days

DOCTYPE = "Day Plan"
SHUTDOWN_ACTIONS = ("tomorrow", "later_this_week", "plan", "drop", "keep")


# reading


def _plan_name(date, user=None):
	return frappe.db.get_value(DOCTYPE, {"user": user or frappe.session.user, "date": getdate(date)}, "name")


def _previous_plan(date, user=None):
	name = frappe.db.get_value(
		DOCTYPE,
		{"user": user or frappe.session.user, "date": ("<", getdate(date))},
		"name",
		order_by="date desc",
	)
	return frappe.get_doc(DOCTYPE, name) if name else None


def _todo_rows(names):
	if not names:
		return {}
	rows = frappe.get_all(
		"ToDo",
		filters={"name": ("in", list(names))},
		fields=personal_todos.todo_fields(),
	)
	return {row.name: row for row in rows}


def live_outcome(item, todo):
	"""Done/Dropped follow the ToDo itself; Moved/Open come from the plan."""
	if todo is None:
		return item.outcome or "Open"
	if todo.status == "Closed":
		return "Done"
	if todo.status == "Cancelled":
		return "Dropped"
	return item.outcome or "Open"


def _fixed_at(doc):
	return doc.frozen_at or doc.confirmed_at


def is_planned(doc, item):
	"""Was the item on the plan when it was fixed (start of day or FREEZE_HOUR)?"""
	fixed = _fixed_at(doc)
	return bool(fixed and item.added_at and get_datetime(item.added_at) <= get_datetime(fixed))


def _estimate(todo, item):
	return cint((todo or {}).get("cockpit_estimate_minutes")) or cint(item.estimate_minutes) or None


def _serialize_items(doc):
	todos = _todo_rows([row.todo for row in doc.items])
	items = []
	for row in doc.items:
		todo = todos.get(row.todo)
		estimate = _estimate(todo, row)
		items.append(
			{
				"todo": row.todo,
				"summary": personal_todos._summary(todo.description) if todo else row.summary,
				"estimate_minutes": estimate,
				"important": bool(todo and todo.get("cockpit_important")),
				"date": todo.date if todo else None,
				"overdue": bool(todo and todo.date and getdate(todo.date) < getdate(today()) and todo.status == "Open"),
				"carried_over": bool(row.carried_over),
				"rollover_count": cint(row.rollover_count),
				"outcome": live_outcome(row, todo),
				"moved_to": row.moved_to,
				"planned": is_planned(doc, row),
				"reschedule_count": cint(todo.get("cockpit_reschedule_count")) if todo else 0,
			}
		)
	return items


def calibration(user=None):
	"""How long ToDos took in focus compared with their estimate, over the last 90 days."""
	user = user or frappe.session.user
	if not frappe.get_meta("ToDo").has_field("cockpit_actual_minutes"):
		return None
	rows = frappe.get_all(
		"ToDo",
		filters={
			"allocated_to": user,
			"status": "Closed",
			"cockpit_closed_on": (">=", add_days(getdate(today()), -CALIBRATION_DAYS)),
			"cockpit_estimate_minutes": (">", 0),
			"cockpit_actual_minutes": (">", 0),
		},
		fields=["cockpit_estimate_minutes", "cockpit_actual_minutes"],
	)
	if len(rows) < CALIBRATION_MIN_SAMPLES:
		return {"samples": len(rows), "factor": None}
	estimate = sum(cint(r.cockpit_estimate_minutes) for r in rows)
	actual = sum(cint(r.cockpit_actual_minutes) for r in rows)
	return {"samples": len(rows), "factor": round(actual / estimate, 1) if estimate else None}


def _candidates(date, plan_todos):
	"""Open ToDos worth considering for the day, grouped; leftovers first."""
	date = getdate(date)
	week_end = date + timedelta(days=6 - date.weekday())
	open_todos = [t for t in personal_todos.get_my_todos() if t["name"] not in plan_todos]
	by_name = {t["name"]: t for t in open_todos}
	used = set()

	leftovers = []
	previous = _previous_plan(date)
	if previous:
		todos = _todo_rows([row.todo for row in previous.items])
		for row in previous.items:
			todo = todos.get(row.todo)
			if row.todo in by_name and live_outcome(row, todo) == "Open":
				leftovers.append({**by_name[row.todo], "rollover_count": cint(row.rollover_count) + 1, "from_date": previous.date})
				used.add(row.todo)

	def pick(rule):
		group = [t for t in open_todos if t["name"] not in used and rule(t)]
		used.update(t["name"] for t in group)
		return group

	overdue = pick(lambda t: t["date"] and getdate(t["date"]) < date)
	due_today = pick(lambda t: t["date"] and getdate(t["date"]) == date)
	important = pick(lambda t: t["important"])
	this_week = pick(lambda t: t["date"] and getdate(t["date"]) <= week_end)
	return [
		{"key": "leftovers", "label": "Not finished last time", "items": leftovers},
		{"key": "overdue", "label": "Overdue", "items": overdue},
		{"key": "due_today", "label": "Due today", "items": due_today},
		{"key": "important", "label": "Important to you", "items": important},
		{"key": "this_week", "label": "Due this week", "items": this_week},
	]


def get_day_plan(date=None):
	date = getdate(date or today())
	name = _plan_name(date)
	doc = frappe.get_doc(DOCTYPE, name) if name else None
	items = _serialize_items(doc) if doc else []
	active = [i for i in items if i["outcome"] not in ("Moved", "Dropped")]
	planned_minutes = sum(i["estimate_minutes"] or DEFAULT_ESTIMATE_MINUTES for i in active if i["outcome"] != "Done")
	return {
		"date": date,
		"today": getdate(today()),
		"exists": bool(doc),
		"status": doc.status if doc else "Draft",
		"confirmed_at": doc.confirmed_at if doc else None,
		"fixed_at": _fixed_at(doc) if doc else None,
		"auto_fixed": bool(doc and doc.auto_frozen),
		"shutdown_at": doc.shutdown_at if doc else None,
		"reflection": doc.reflection if doc else "",
		"items": items,
		"candidates": _candidates(date, {i["todo"] for i in items}),
		"cap": MY_DAY_CAP,
		"capacity_minutes": (doc.capacity_minutes if doc and doc.capacity_minutes else CAPACITY_MINUTES),
		"remaining_minutes": planned_minutes,
		"unestimated": sum(1 for i in active if i["outcome"] != "Done" and not i["estimate_minutes"]),
		"default_estimate_minutes": DEFAULT_ESTIMATE_MINUTES,
		"rollover_decide": ROLLOVER_DECIDE,
		"calibration": calibration(),
		"next_working_day": add_working_days(add_days(date, 1), 0),
	}


def get_day_state():
	"""Small summary for the dashboard's call to action."""
	name = _plan_name(today())
	if not name:
		return {"status": "None", "planned": 0, "done": 0}
	doc = frappe.get_doc(DOCTYPE, name)
	items = _serialize_items(doc)
	return {
		"status": doc.status,
		"planned": sum(1 for i in items if i["outcome"] not in ("Moved", "Dropped")),
		"done": sum(1 for i in items if i["outcome"] == "Done"),
	}


# writing


def _get_or_create(date):
	date = getdate(date)
	name = _plan_name(date)
	if name:
		return frappe.get_doc(DOCTYPE, name)
	doc = frappe.get_doc(
		{"doctype": DOCTYPE, "user": frappe.session.user, "date": date, "status": "Draft", "capacity_minutes": CAPACITY_MINUTES}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _save(doc):
	doc.flags.ignore_permissions = True
	doc.save()


def _check_date(date):
	date = getdate(date or today())
	if date < getdate(today()):
		frappe.throw(_("Past days cannot be planned any more."))
	return date


def _append(doc, todo, carried_from=None):
	if any(row.todo == todo.name for row in doc.items):
		return False
	rollover = 0
	if carried_from is not None:
		rollover = cint(carried_from.rollover_count) + 1
	else:
		previous = _previous_plan(doc.date, doc.user)
		if previous:
			before = next((row for row in previous.items if row.todo == todo.name), None)
			if before and live_outcome(before, frappe._dict(status=todo.status)) == "Open":
				rollover = cint(before.rollover_count) + 1
	doc.append(
		"items",
		{
			"todo": todo.name,
			"summary": personal_todos._summary(todo.description)[:140],
			"added_at": now_datetime(),
			"estimate_minutes": todo.get("cockpit_estimate_minutes"),
			"important_at_plan": cint(todo.get("cockpit_important")),
			"carried_over": 1 if rollover else 0,
			"rollover_count": rollover,
			"outcome": "Open",
		},
	)
	return True


def add_to_day(todo, date=None):
	date = _check_date(date)
	doc_todo = personal_todos._get_my_todo(todo)
	if doc_todo.status != "Open":
		frappe.throw(_("Only open ToDos can be planned."))
	doc = _get_or_create(date)
	if doc.status == "Closed":
		frappe.throw(_("This day is already shut down."))
	if _append(doc, doc_todo):
		_save(doc)
	return get_day_plan(date)


def remove_from_day(todo, date=None):
	date = _check_date(date)
	name = _plan_name(date)
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.status == "Closed":
			frappe.throw(_("This day is already shut down."))
		doc.items = [row for row in doc.items if row.todo != todo]
		for index, row in enumerate(doc.items, start=1):
			row.idx = index
		_save(doc)
	return get_day_plan(date)


def move_in_day(todo, direction, date=None):
	date = _check_date(date)
	name = _plan_name(date)
	if not name:
		frappe.throw(_("Nothing planned for this day."))
	doc = frappe.get_doc(DOCTYPE, name)
	rows = list(doc.items)
	index = next((i for i, row in enumerate(rows) if row.todo == todo), None)
	if index is None:
		frappe.throw(_("This ToDo is not on the plan."))
	target = index - 1 if direction == "up" else index + 1
	if 0 <= target < len(rows):
		rows[index], rows[target] = rows[target], rows[index]
		for position, row in enumerate(rows, start=1):
			row.idx = position
		doc.items = rows
		_save(doc)
	return get_day_plan(date)


def start_day(date=None):
	"""Fix the plan: what is on it now counts as planned (#1561)."""
	date = _check_date(date)
	if date != getdate(today()):
		frappe.throw(_("A day can only be started on the day itself."))
	doc = _get_or_create(date)
	if not doc.items:
		frappe.throw(_("Add at least one ToDo first."))
	if doc.status == "Draft":
		now = now_datetime()
		doc.status = "Confirmed"
		doc.confirmed_at = now
		if not doc.frozen_at:
			doc.frozen_at = now
		_save(doc)
	return get_day_plan(date)


def shutdown_day(decisions=None, reflection=None, date=None):
	"""Close the day: every open item gets a decision; nothing rolls over silently."""
	date = getdate(date or today())
	name = _plan_name(date)
	if not name:
		frappe.throw(_("Nothing planned for this day."))
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.status == "Closed":
		frappe.throw(_("This day is already shut down."))
	if isinstance(decisions, str):
		decisions = frappe.parse_json(decisions)
	decisions = {d["todo"]: d for d in (decisions or [])}

	todos = _todo_rows([row.todo for row in doc.items])
	open_rows = [row for row in doc.items if live_outcome(row, todos.get(row.todo)) == "Open"]
	missing = [row.summary for row in open_rows if row.todo not in decisions]
	if missing:
		frappe.throw(_("Please decide on every open ToDo: {0}").format(", ".join(missing[:3])))

	next_day = add_working_days(add_days(date, 1), 0)
	for row in doc.items:
		outcome = live_outcome(row, todos.get(row.todo))
		if outcome != "Open":
			row.outcome = outcome
			continue
		decision = decisions[row.todo]
		action = decision.get("action")
		if action not in SHUTDOWN_ACTIONS:
			frappe.throw(_("Unknown decision: {0}").format(action))
		if action == "keep":
			continue
		if action == "drop":
			personal_todos.decide_todo(row.todo, "drop", reason=decision.get("reason") or "Decided at shutdown")
			row.outcome = "Dropped"
			continue
		if action == "tomorrow":
			moved = personal_todos.decide_todo(row.todo, "plan", date=str(next_day))
			tomorrow = _get_or_create(next_day)
			_append(tomorrow, personal_todos._get_my_todo(row.todo), carried_from=row)
			_save(tomorrow)
		elif action == "later_this_week":
			moved = personal_todos.decide_todo(row.todo, "later_this_week")
		else:
			moved = personal_todos.decide_todo(row.todo, "plan", date=decision.get("date"))
		row.outcome = "Moved"
		row.moved_to = moved["date"]

	doc.status = "Closed"
	doc.shutdown_at = now_datetime()
	if not doc.frozen_at:
		doc.frozen_at = doc.shutdown_at
	doc.reflection = (reflection or "").strip()[:500]
	_save(doc)
	return get_day_plan(date)


def freeze_day_plans():
	"""Scheduler (daily at FREEZE_HOUR): plans nobody started are fixed as they are."""
	now = now_datetime()
	for name in frappe.get_all(DOCTYPE, filters={"date": getdate(today()), "status": "Draft", "frozen_at": ("is", "not set")}, pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.items:
			doc.frozen_at = now
			doc.auto_frozen = 1
			_save(doc)
	frappe.db.commit()
