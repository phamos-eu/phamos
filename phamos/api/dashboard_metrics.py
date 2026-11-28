# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Doctype-neutral helpers for cockpit dashboards: windows, buckets, percentiles.

Rows are dicts with datetime-like values; field names are parameters, so the same
helpers serve ToDos (cockpit_closed_on) and later other records.
"""

import math
from datetime import timedelta

from frappe import _
from frappe.utils import get_datetime


def _dt(value):
	return get_datetime(value) if value else None


def in_window(value, start, end):
	value = _dt(value)
	return bool(value and start <= value < end)


def open_at(rows, point, created_field="creation", done_field="cockpit_closed_on"):
	"""Rows that existed at `point` and were not done yet."""
	count = 0
	for row in rows:
		created = _dt(row.get(created_field))
		done = _dt(row.get(done_field))
		if created and created <= point and (done is None or done > point):
			count += 1
	return count


def percentile(values, p):
	"""Nearest-rank percentile (p in 0..100) of a list of numbers; None when empty."""
	values = sorted(v for v in values if v is not None)
	if not values:
		return None
	rank = max(1, math.ceil(p / 100 * len(values)))
	return values[rank - 1]


def age_buckets(rows, now, buckets, created_field="creation"):
	"""Count rows per age bucket ((label, min_days, max_days or None), ...)."""
	# Labels go out translated (#1605); the buckets are matched by position, never by label.
	result = [{"label": _(label), "value": 0} for label, _min, _max in buckets]
	for row in rows:
		created = _dt(row.get(created_field))
		if not created:
			continue
		age = (now - created).days
		for index, (_label, low, high) in enumerate(buckets):
			if age >= low and (high is None or age <= high):
				result[index]["value"] += 1
				break
	return result


def period_windows(now, days):
	"""Bar windows for a dashboard period: daily for 7 days, weekly otherwise (oldest first)."""
	end = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
	if days <= 7:
		return [
			# strftime gives the English abbreviation; it is translated like any other label (#1605).
			(_(start.strftime("%a")), start, start + timedelta(days=1))
			for start in (end - timedelta(days=offset) for offset in range(days, 0, -1))
		]
	weeks = math.ceil(days / 7)
	last_day = end - timedelta(days=1)
	monday = last_day - timedelta(days=last_day.weekday())
	windows = []
	for offset in range(weeks - 1, -1, -1):
		start = monday - timedelta(weeks=offset)
		windows.append((_("W{0}").format(start.isocalendar()[1]), start, min(start + timedelta(days=7), end)))
	return windows
