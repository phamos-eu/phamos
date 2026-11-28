# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Self-set ToDo challenges of the Personal Cockpit (phamos/phamos#1557).

"Close 2 ToDos a day for the next 10 working days": opt-in, private, built to forgive.
A working day counts when the user closed at least the target. A missed day uses a joker
while there is one; without a joker it can still be repaired by closing target + shortfall
on the next working day. A challenge ends "Completed" (every day counted) or "Ended" — never
"failed", and nothing resets to zero.

Counted closes: ToDos allocated to and closed by the user on that day, not created and
closed within MICRO_MINUTES (quick wins), never dropped (Cancelled) ones. "Important per day"
counts only ToDos flagged important.
"""

import statistics
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate, today

from phamos.cockpits.defaults import (
	BASELINE_WORKING_DAYS,
	CHALLENGE_KINDS,
	CHALLENGE_LENGTHS,
	JOKER_EVERY_DAYS,
	MAX_JOKERS,
	MAX_TARGET_PER_DAY,
	MICRO_MINUTES,
	SPONTANEOUS_MICRO_MAX,
	SUGGESTION_MAX,
	SUGGESTION_STRETCH,
)
from phamos.cockpits.workdays import MAX_SEARCH_DAYS, days_off, is_working_day

DOCTYPE = "ToDo Challenge"
COUNTED = ("Met", "Joker", "Repaired")
SPLIT = "Planned and spontaneous"


# working days and closes


def working_days_from(start, count, user):
	"""The first `count` working days from `start` (inclusive)."""
	start = getdate(start)
	off = days_off(user, start, start + timedelta(days=count * 2 + MAX_SEARCH_DAYS))
	days = []
	day = start
	while len(days) < count and (day - start).days <= count * 2 + MAX_SEARCH_DAYS:
		if is_working_day(day, off):
			days.append(day)
		day += timedelta(days=1)
	return days


def working_days_before(end, count, user):
	"""The last `count` working days before `end` (exclusive), oldest first."""
	end = getdate(end)
	start = end - timedelta(days=count * 2 + MAX_SEARCH_DAYS)
	off = days_off(user, start, end)
	days = []
	day = end - timedelta(days=1)
	while len(days) < count and day >= start:
		if is_working_day(day, off):
			days.append(day)
		day -= timedelta(days=1)
	return list(reversed(days))


def closes_by_day(user, start, end, kind=CHALLENGE_KINDS[0]):
	"""{date: counted closes} for the user between start and end (inclusive)."""
	if not frappe.get_meta("ToDo").has_field("cockpit_closed_on"):
		return {}
	important = "and `cockpit_important` = 1" if kind == "Important per day" else ""
	rows = frappe.db.sql(
		f"""
		select date(`cockpit_closed_on`) as day, count(*) as closes
		from `tabToDo`
		where `allocated_to` = %(user)s
			and `cockpit_closed_by` = %(user)s
			and `status` = 'Closed'
			and `cockpit_closed_on` >= %(start)s
			and `cockpit_closed_on` < %(end)s
			and timestampdiff(minute, `creation`, `cockpit_closed_on`) >= %(micro)s
			{important}
		group by date(`cockpit_closed_on`)
		""",
		{
			"user": user,
			"start": getdate(start),
			"end": add_days(getdate(end), 1),
			"micro": MICRO_MINUTES,
		},
		as_dict=True,
	)
	return {getdate(row.day): cint(row.closes) for row in rows}


def split_by_day(user, start, end):
	"""{date: {"planned": p, "spontaneous": s}} of the user's closes (#1561).

	Planned: on that day's plan when it was fixed. Spontaneous: the rest; quick wins (created and
	closed within MICRO_MINUTES) count as spontaneous too, but at most SPONTANEOUS_MICRO_MAX a day.
	"""
	from phamos.api.personal_day_plan import planned_pairs

	if not frappe.get_meta("ToDo").has_field("cockpit_closed_on"):
		return {}
	rows = frappe.db.sql(
		"""
		select `name`, date(`cockpit_closed_on`) as day,
			timestampdiff(minute, `creation`, `cockpit_closed_on`) < %(micro)s as quick
		from `tabToDo`
		where `allocated_to` = %(user)s
			and `cockpit_closed_by` = %(user)s
			and `status` = 'Closed'
			and `cockpit_closed_on` >= %(start)s
			and `cockpit_closed_on` < %(end)s
		""",
		{"user": user, "start": getdate(start), "end": add_days(getdate(end), 1), "micro": MICRO_MINUTES},
		as_dict=True,
	)
	planned = planned_pairs(user, start, end)
	days = {}
	quick_used = {}
	for row in rows:
		day = getdate(row.day)
		counts = days.setdefault(day, {"planned": 0, "spontaneous": 0})
		if (day, row.name) in planned:
			counts["planned"] += 1
		elif row.quick:
			if quick_used.get(day, 0) < SPONTANEOUS_MICRO_MAX:
				quick_used[day] = quick_used.get(day, 0) + 1
				counts["spontaneous"] += 1
		else:
			counts["spontaneous"] += 1
	return days


def day_counts(doc, start, end):
	"""{date: {"closes", "planned", "spontaneous"}} as the challenge counts them."""
	if doc.kind == SPLIT:
		return {
			day: {"closes": c["planned"] + c["spontaneous"], **c}
			for day, c in split_by_day(doc.user, start, end).items()
		}
	return {day: {"closes": n, "planned": 0, "spontaneous": 0} for day, n in closes_by_day(doc.user, start, end, doc.kind).items()}


EMPTY = {"closes": 0, "planned": 0, "spontaneous": 0}


def is_met(doc, counts):
	if doc.kind == SPLIT:
		return counts["planned"] >= cint(doc.target_planned) and counts["spontaneous"] >= cint(doc.target_spontaneous)
	return counts["closes"] >= cint(doc.target_per_day)


def repair_needs(doc, row):
	"""What the next working day must reach to repair a missed day."""
	if doc.kind == SPLIT:
		tp, ts = cint(doc.target_planned), cint(doc.target_spontaneous)
		return {
			"planned": tp + max(tp - cint(row.planned_closes), 0),
			"spontaneous": ts + max(ts - cint(row.spontaneous_closes), 0),
		}
	target = cint(doc.target_per_day)
	return {"closes": target + max(target - cint(row.closes), 0)}


def reaches(counts, needs):
	return all(counts.get(key, 0) >= value for key, value in needs.items())


def jokers_for(working_days):
	return min(MAX_JOKERS, max(1, cint(working_days) // JOKER_EVERY_DAYS))


# evaluation


def evaluate(doc, on=None):
	"""Settle every past working day of an active challenge; idempotent. Returns True if changed."""
	if doc.status != "Active":
		return False
	on = getdate(on or today())
	schedule = working_days_from(doc.start_date, cint(doc.working_days), doc.user)
	if not schedule:
		return False
	counts = day_counts(doc, schedule[0], min(schedule[-1], on))
	target = cint(doc.target_per_day)
	rows = {getdate(row.date): row for row in doc.days}
	jokers_used = sum(1 for row in doc.days if row.result == "Joker")
	changed = False

	def day_row(day, result):
		c = counts.get(day, EMPTY)
		return {
			"date": day,
			"closes": c["closes"],
			"planned_closes": c["planned"],
			"spontaneous_closes": c["spontaneous"],
			"target": target,
			"result": result,
		}

	for day in schedule:
		if day >= on or day in rows:
			continue
		if is_met(doc, counts.get(day, EMPTY)):
			result = "Met"
		elif jokers_used < cint(doc.jokers_allowed):
			result, jokers_used = "Joker", jokers_used + 1
		else:
			result = "Missed"
		rows[day] = doc.append("days", day_row(day, result))
		changed = True

	# A missed day is repaired when the next working day also makes up the shortfall, once that day is over.
	for index, day in enumerate(schedule[:-1]):
		row = rows.get(day)
		following = schedule[index + 1]
		if row and row.result == "Missed" and following < on:
			if reaches(counts.get(following, EMPTY), repair_needs(doc, row)):
				row.result = "Repaired"
				changed = True

	last = schedule[-1]
	missed = any(row.result == "Missed" for row in rows.values())
	if last < on:
		doc.status = "Ended" if missed else "Completed"
		doc.ended_on = last
		changed = True
	elif last == on and not missed and is_met(doc, counts.get(on, EMPTY)) and all(d in rows for d in schedule[:-1]):
		doc.append("days", day_row(on, "Met"))
		doc.status = "Completed"
		doc.ended_on = on
		changed = True

	if changed:
		doc.days = sorted(doc.days, key=lambda r: getdate(r.date))
		for index, row in enumerate(doc.days, start=1):
			row.idx = index
		doc.flags.ignore_permissions = True
		doc.save()
	return changed


def _streaks(results):
	"""Current and best run of counted days (results in date order)."""
	best = current = 0
	for result in results:
		current = current + 1 if result in COUNTED else 0
		best = max(best, current)
	return current, best


def serialize(doc, on=None):
	on = getdate(on or today())
	schedule = working_days_from(doc.start_date, cint(doc.working_days), doc.user)
	target = cint(doc.target_per_day)
	rows = {getdate(row.date): row for row in doc.days}
	live = day_counts(doc, on, on).get(on, EMPTY) if doc.status == "Active" else EMPTY
	in_schedule_today = on in schedule and on not in rows
	met_today = in_schedule_today and is_met(doc, live)

	days = []
	for day in schedule:
		row = rows.get(day)
		if row:
			days.append(
				{
					"date": day,
					"closes": cint(row.closes),
					"planned": cint(row.planned_closes),
					"spontaneous": cint(row.spontaneous_closes),
					"target": target,
					"result": row.result,
				}
			)
		elif day == on and doc.status == "Active":
			days.append({"date": day, "closes": live["closes"], "planned": live["planned"], "spontaneous": live["spontaneous"], "target": target, "result": "Today", "met": met_today})
		else:
			days.append({"date": day, "closes": None, "target": target, "result": "Upcoming"})

	settled = [d["result"] for d in days if d["result"] in COUNTED or d["result"] == "Missed"]
	current, best = _streaks(settled + (["Met"] if met_today else []))
	counted = sum(1 for d in days if d["result"] in COUNTED) + (1 if met_today else 0)
	jokers_used = sum(1 for d in days if d["result"] == "Joker")

	repair = None
	if in_schedule_today:
		index = schedule.index(on)
		previous = rows.get(schedule[index - 1]) if index else None
		if previous and previous.result == "Missed":
			needs = repair_needs(doc, previous)
			repair = {"date": previous.date, "needs": needs, "reached": reaches(live, needs)}

	split = doc.kind == SPLIT
	remaining = (
		max(cint(doc.target_planned) - live["planned"], 0) + max(cint(doc.target_spontaneous) - live["spontaneous"], 0)
		if split
		else max(target - live["closes"], 0)
	)
	last_settled = settled[-1] if settled else None
	return {
		"name": doc.name,
		"title": doc.title,
		"kind": doc.kind,
		"split": split,
		"status": doc.status,
		"target_per_day": target,
		"target_planned": cint(doc.target_planned),
		"target_spontaneous": cint(doc.target_spontaneous),
		"start_date": getdate(doc.start_date),
		"end_date": getdate(doc.end_date),
		"ended_on": doc.ended_on,
		"working_days": cint(doc.working_days),
		"baseline_per_day": doc.baseline_per_day,
		"counted_days": counted,
		"jokers_allowed": cint(doc.jokers_allowed),
		"jokers_left": max(cint(doc.jokers_allowed) - jokers_used, 0),
		"current_streak": current,
		"best_streak": best,
		"today": {
			"in_schedule": in_schedule_today,
			"closes": live["closes"],
			"planned": live["planned"],
			"spontaneous": live["spontaneous"],
			"target": target,
			"remaining": remaining,
			"met": met_today,
			"repair": repair,
		},
		"welcome_back": last_settled in ("Missed", "Joker") and in_schedule_today,
		"not_started": getdate(doc.start_date) > on,
		"days": days,
	}


# API


def _get_my_challenge(name):
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.user != frappe.session.user:
		frappe.throw(_("This challenge is not yours."), frappe.PermissionError)
	return doc


def get_challenges():
	"""My active challenges (settled up to today) and the five most recent finished ones."""
	user = frappe.session.user
	active = []
	for name in frappe.get_all(DOCTYPE, filters={"user": user, "status": "Active"}, order_by="creation asc", pluck="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		evaluate(doc)
		if doc.status == "Active":
			active.append(serialize(doc))
	recent = [
		serialize(frappe.get_doc(DOCTYPE, name))
		for name in frappe.get_all(
			DOCTYPE,
			filters={"user": user, "status": ("in", ("Completed", "Ended"))},
			order_by="modified desc",
			limit=5,
			pluck="name",
		)
	]
	return {"active": active, "recent": recent}


def next_monday(on=None):
	on = getdate(on or today())
	return on + timedelta(days=(7 - on.weekday()) % 7 or 7)


def _stretch(baseline):
	return min(max(round(baseline * SUGGESTION_STRETCH), 1), SUGGESTION_MAX)


def suggest_challenge(kind=CHALLENGE_KINDS[0]):
	"""A target from my own history: median per working day × 1.2, between 1 and 5."""
	if kind not in CHALLENGE_KINDS:
		frappe.throw(_("Unknown kind: {0}").format(kind))
	user = frappe.session.user
	on = getdate(today())
	window = working_days_before(on, BASELINE_WORKING_DAYS, user)
	baseline = planned = spontaneous = 0.0
	if window and kind == SPLIT:
		split = split_by_day(user, window[0], window[-1])
		planned = float(statistics.median(split.get(day, {}).get("planned", 0) for day in window))
		spontaneous = float(statistics.median(split.get(day, {}).get("spontaneous", 0) for day in window))
		baseline = planned + spontaneous
	elif window:
		closes = closes_by_day(user, window[0], window[-1], kind)
		baseline = float(statistics.median(closes.get(day, 0) for day in window))
	return {
		"kind": kind,
		"baseline_per_day": round(baseline, 1),
		"suggested": _stretch(baseline),
		"baseline_planned": round(planned, 1),
		"baseline_spontaneous": round(spontaneous, 1),
		"suggested_planned": _stretch(planned),
		"suggested_spontaneous": _stretch(spontaneous),
		"today": on,
		"today_is_working_day": is_working_day(on, days_off(user, on, on)),
		"next_monday": next_monday(on),
		"lengths": list(CHALLENGE_LENGTHS),
		"kinds": list(CHALLENGE_KINDS),
		"max_target": MAX_TARGET_PER_DAY,
	}


def default_title(kind, target, working_days, planned=0, spontaneous=0):
	if kind == SPLIT:
		return _("{0} planned + {1} spontaneous a day for {2} working days").format(planned, spontaneous, working_days)
	if kind == "Important per day":
		return _("{0} important a day for {1} working days").format(target, working_days)
	return _("Close {0} a day for {1} working days").format(target, working_days)


def create_challenge(
	kind, target_per_day=None, working_days=10, start_date=None, title=None, target_planned=None, target_spontaneous=None
):
	if kind not in CHALLENGE_KINDS:
		frappe.throw(_("Unknown kind: {0}").format(kind))
	planned = spontaneous = 0
	if kind == SPLIT:
		planned, spontaneous = cint(target_planned), cint(target_spontaneous)
		if planned < 0 or spontaneous < 0 or planned + spontaneous < 1:
			frappe.throw(_("Pick at least one planned or spontaneous ToDo a day."))
		target = planned + spontaneous
	else:
		target = cint(target_per_day)
	if target < 1 or target > MAX_TARGET_PER_DAY:
		frappe.throw(_("Pick a target between 1 and {0} a day.").format(MAX_TARGET_PER_DAY))
	working_days = cint(working_days)
	if working_days not in CHALLENGE_LENGTHS:
		frappe.throw(_("A challenge runs for {0} working days.").format(", ".join(map(str, CHALLENGE_LENGTHS))))
	start = getdate(start_date or today())
	if start < getdate(today()):
		frappe.throw(_("A challenge cannot start in the past."))
	user = frappe.session.user
	if frappe.db.exists(DOCTYPE, {"user": user, "kind": kind, "status": "Active"}):
		frappe.throw(_("You already have a running challenge of this kind."))

	schedule = working_days_from(start, working_days, user)
	if len(schedule) < working_days:
		frappe.throw(_("Not enough working days found after {0}.").format(frappe.format(start, "Date")))
	suggestion = suggest_challenge(kind)
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"user": user,
			"title": (title or "").strip()[:140] or default_title(kind, target, working_days, planned, spontaneous),
			"kind": kind,
			"target_per_day": target,
			"target_planned": planned,
			"target_spontaneous": spontaneous,
			"status": "Active",
			"start_date": schedule[0],
			"working_days": working_days,
			"end_date": schedule[-1],
			"jokers_allowed": jokers_for(working_days),
			"baseline_per_day": suggestion["baseline_per_day"],
		}
	)
	doc.insert(ignore_permissions=True)
	return serialize(doc)


def end_challenge(name):
	"""Stop a running challenge early. It ends; nothing is marked as failed."""
	doc = _get_my_challenge(name)
	evaluate(doc)
	if doc.status == "Active":
		doc.status = "Ended"
		doc.ended_on = getdate(today())
		doc.flags.ignore_permissions = True
		doc.save()
	return serialize(doc)


def evaluate_all_challenges():
	"""Scheduler (daily): settle yesterday for every running challenge."""
	for name in frappe.get_all(DOCTYPE, filters={"status": "Active"}, pluck="name"):
		try:
			evaluate(frappe.get_doc(DOCTYPE, name))
		except Exception:
			frappe.log_error(frappe.get_traceback(), "ToDo challenge evaluation")
	frappe.db.commit()
