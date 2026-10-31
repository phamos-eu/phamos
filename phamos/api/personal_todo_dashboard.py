# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""ToDo dashboard of the Personal Cockpit (phamos/phamos#1553).

Answers "am I closing or hoarding?" for the session user only: the open vs closed ratio,
how the backlog moved, how long ToDos take, how old the open ones are, and which ones
need a decision. Closures count when I closed them (`cockpit_closed_by`); a ToDo closed
or cancelled by someone else (for example an assignment removed by its assigner) is shown
separately and never counted as mine.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, getdate, now_datetime

from phamos.api import dashboard_metrics as dm
from phamos.api import personal_todos
from phamos.cockpits.defaults import AGE_BUCKETS, DASHBOARD_PERIODS, MICRO_MINUTES, OLDEST_LIMIT


def _fields():
	return personal_todos.todo_fields()


def _load_rows(since):
	"""My ToDos that are open, or were created or closed since `since`. Never Cancelled-by-others filtering here."""
	user = frappe.session.user
	fields = _fields()
	open_rows = frappe.get_list(
		"ToDo",
		filters={"allocated_to": user, "status": "Open"},
		fields=fields,
		limit_page_length=0,
	)
	recent = frappe.get_list(
		"ToDo",
		filters={"allocated_to": user, "status": ("!=", "Open")},
		or_filters={"creation": (">=", since), "cockpit_closed_on": (">=", since)},
		fields=fields,
		limit_page_length=0,
	)
	return open_rows, recent


def _is_mine(row):
	return row.get("cockpit_closed_by") == frappe.session.user


def _minutes_between(start, end):
	return (get_datetime(end) - get_datetime(start)).total_seconds() / 60


def _window_stats(rows, start, end):
	created = closed = dropped = 0
	for row in rows:
		if dm.in_window(row.get("creation"), start, end):
			created += 1
		if not _is_mine(row) or not dm.in_window(row.get("cockpit_closed_on"), start, end):
			continue
		if row.get("status") == "Closed":
			closed += 1
		elif row.get("status") == "Cancelled":
			dropped += 1
	return {"created": created, "closed": closed, "dropped": dropped}


def _brief(row, now):
	created = get_datetime(row.get("creation"))
	return {
		"name": row.get("name"),
		"summary": personal_todos._summary(row.get("description")),
		"date": row.get("date"),
		"age_days": (now - created).days if created else None,
		"reschedule_count": row.get("cockpit_reschedule_count") or 0,
		"first_due_date": row.get("cockpit_first_due_date"),
		"important": bool(row.get("cockpit_important")),
		"stale": personal_todos.is_stale(row, now),
		"overdue": bool(row.get("date") and getdate(row.get("date")) < getdate(now)),
	}


def get_todo_dashboard(period=30):
	period = cint(period) or 30
	if period not in DASHBOARD_PERIODS:
		frappe.throw(_("Period must be one of {0} days.").format(", ".join(map(str, DASHBOARD_PERIODS))))
	if not frappe.get_meta("ToDo").has_field("cockpit_closed_on"):
		frappe.throw(_("The Personal Cockpit fields are missing on ToDo. Please run bench migrate."))

	now = now_datetime()
	start = now - timedelta(days=period)
	previous_start = start - timedelta(days=period)
	open_rows, recent = _load_rows(previous_start)
	all_rows = open_rows + recent

	current = _window_stats(all_rows, start, now)
	previous = _window_stats(all_rows, previous_start, start)
	current["open"] = len(open_rows)
	previous["open"] = dm.open_at(all_rows, start)
	for window in (current, previous):
		finished = window["closed"] + window["open"]
		window["closed_share"] = round(window["closed"] * 100 / finished, 1) if finished else None

	flow = []
	for label, w_start, w_end in dm.period_windows(now, period):
		stats = _window_stats(all_rows, w_start, w_end)
		stats["label"] = label
		stats["start"] = w_start
		stats["net"] = stats["created"] - stats["closed"] - stats["dropped"]
		flow.append(stats)

	mine_closed = [
		r for r in recent if r.get("status") == "Closed" and _is_mine(r) and dm.in_window(r.get("cockpit_closed_on"), start, now)
	]
	lead_days = [
		(get_datetime(r["cockpit_closed_on"]) - get_datetime(r["creation"])).total_seconds() / 86400 for r in mine_closed
	]
	micro = [r for r in mine_closed if _minutes_between(r["creation"], r["cockpit_closed_on"]) < MICRO_MINUTES]
	important = [r for r in mine_closed if r.get("cockpit_important")]
	by_others = [
		r
		for r in recent
		if r.get("status") != "Open"
		and r.get("cockpit_closed_by")
		and not _is_mine(r)
		and dm.in_window(r.get("cockpit_closed_on"), start, now)
	]

	# Planned vs spontaneous (#1561): planned = on that day's plan when it was fixed.
	planned = _planned_pairs(start, now)

	def is_planned(row):
		return (getdate(row["cockpit_closed_on"]), row["name"]) in planned

	planned_closed = [r for r in mine_closed if is_planned(r)]

	oldest = sorted(open_rows, key=lambda r: get_datetime(r["creation"]))[:OLDEST_LIMIT]
	stale = sorted(
		(r for r in open_rows if personal_todos.is_stale(r, now)),
		key=lambda r: (-(r.get("cockpit_reschedule_count") or 0), get_datetime(r["creation"])),
	)

	day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
	done_today = sorted(
		(
			r
			for r in recent
			if r.get("status") == "Closed" and _is_mine(r) and dm.in_window(r.get("cockpit_closed_on"), day_start, now + timedelta(seconds=1))
		),
		key=lambda r: get_datetime(r["cockpit_closed_on"]),
		reverse=True,
	)
	dropped_today = sum(
		1
		for r in recent
		if r.get("status") == "Cancelled" and _is_mine(r) and dm.in_window(r.get("cockpit_closed_on"), day_start, now + timedelta(seconds=1))
	)

	return {
		"period_days": period,
		"generated_at": now,
		"windows": {"current": current, "previous": previous},
		"flow": flow,
		"lead_time": {
			"p50_days": _round(dm.percentile(lead_days, 50)),
			"p85_days": _round(dm.percentile(lead_days, 85)),
			"sample": len(lead_days),
		},
		"aging": dm.age_buckets(open_rows, now, AGE_BUCKETS),
		"oldest": [_brief(r, now) for r in oldest],
		"stale": [_brief(r, now) for r in stale],
		"stale_count": len(stale),
		"closures": {
			"done": len(mine_closed),
			"dropped": current["dropped"],
			"important": len(important),
			"other": len(mine_closed) - len(important),
			"quick_wins": len(micro),
			"by_others": len(by_others),
			"planned": len(planned_closed),
			"spontaneous": len(mine_closed) - len(planned_closed),
		},
		"today": {
			"done": [
				{
					"name": r["name"],
					"summary": personal_todos._summary(r.get("description")),
					"closed_on": r["cockpit_closed_on"],
					"important": bool(r.get("cockpit_important")),
					"quick_win": _minutes_between(r["creation"], r["cockpit_closed_on"]) < MICRO_MINUTES,
					"planned": is_planned(r),
				}
				for r in done_today
			],
			"dropped": dropped_today,
		},
	}


def _planned_pairs(start, end):
	if not frappe.db.table_exists("Day Plan Item"):
		return set()
	from phamos.api.personal_day_plan import planned_pairs

	return planned_pairs(frappe.session.user, getdate(start), getdate(end))


def _round(value):
	return round(value, 1) if value is not None else None
