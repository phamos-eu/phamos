# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Pure helpers for the Accounting Cockpit statistics and payment calendar (#1369).

No database access: callers pass dates and plain rows, so every rule here runs in a unit
test. Windows are half-open `[start, end)` date ranges in calendar months; amounts are in
company currency.
"""

import math
from datetime import date, timedelta

from frappe.utils import getdate

from phamos.api.dashboard_metrics import percentile

MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# A month is a peak when it exceeds mean + SPIKE_SIGMA × σ of the other trailing months,
# or SPIKE_AVG3_FACTOR × the average of the three months before it.
SPIKE_SIGMA = 2
SPIKE_AVG3_FACTOR = 1.5
# Same month last year within ± this share → "recurring" (insurance, annual licences).
RECURRING_TOLERANCE = 0.2
SPIKE_WINDOW = 12

# (key, label, theme) for unpaid approved receipts, by days until due (negative = overdue).
AGING_BUCKETS = (
	("overdue_30", "Overdue > 30 days", "red"),
	("overdue", "Overdue 1–30 days", "red"),
	("due_7", "Due within 7 days", "amber"),
	("due_30", "Due in 8–30 days", "blue"),
	("later", "Due later", "green"),
	("none", "No due date", "gray"),
)


def month_start(value):
	value = getdate(value)
	return date(value.year, value.month, 1)


def add_months(value, months):
	"""First day of the month `months` away from `value`'s month."""
	value = month_start(value)
	index = value.year * 12 + value.month - 1 + months
	return date(index // 12, index % 12 + 1, 1)


def month_label(start, with_year=False):
	label = MONTH_NAMES[start.month - 1]
	return f"{label} {start.year}" if with_year else label


def month_windows(today, months=12):
	"""`months` calendar months ending with the current one, oldest first.

	Each item is `{label, start, end, mtd}`; `end` is exclusive and `mtd` marks the
	current, still running month.
	"""
	today = getdate(today)
	current = month_start(today)
	windows = []
	for offset in range(months - 1, -1, -1):
		start = add_months(current, -offset)
		windows.append(
			{
				"label": month_label(start, with_year=start.month == 1 or offset == months - 1),
				"start": start,
				"end": add_months(start, 1),
				"mtd": offset == 0,
			}
		)
	return windows


def _day_range_label(start, end):
	last = end - timedelta(days=1)
	if last < start:
		return f"{MONTH_NAMES[start.month - 1]} (no days yet)"
	if last == start:
		return f"{start.day} {MONTH_NAMES[start.month - 1]}"
	return f"{start.day}–{last.day} {MONTH_NAMES[start.month - 1]}"


def comparison_windows(today):
	"""Windows the stat tiles compare the running month against.

	- current: month to date, including today
	- previous_to_date: the previous month cut at the same day (capped at its last day)
	- previous: the full previous month
	- avg3: the three full months before the current one (values are divided by `divisor`)
	- last_year: the same month a year ago, full
	"""
	today = getdate(today)
	current = month_start(today)
	previous = add_months(current, -1)
	cut = min(previous + timedelta(days=today.day), current)
	avg3_start = add_months(current, -3)
	last_year = add_months(current, -12)
	return {
		"current": {"label": _day_range_label(current, today + timedelta(days=1)), "start": current, "end": today + timedelta(days=1), "divisor": 1},
		"previous_to_date": {"label": _day_range_label(previous, cut), "start": previous, "end": cut, "divisor": 1},
		"previous": {"label": month_label(previous, with_year=True), "start": previous, "end": current, "divisor": 1},
		"avg3": {
			"label": f"{month_label(avg3_start)}–{month_label(previous)} avg",
			"start": avg3_start,
			"end": current,
			"divisor": 3,
		},
		"last_year": {"label": month_label(last_year, with_year=True), "start": last_year, "end": add_months(last_year, 1), "divisor": 1},
	}


def in_range(value, start, end):
	value = getdate(value) if value else None
	return bool(value and start <= value < end)


def sum_rows(rows, start, end, date_field, value_field=None):
	"""Sum `value_field` (or count rows when None) of rows whose date lies in [start, end)."""
	total = 0
	for row in rows:
		if in_range(row.get(date_field), start, end):
			total += 1 if value_field is None else (row.get(value_field) or 0)
	return total


def _mean(values):
	return sum(values) / len(values) if values else 0


def _stdev(values):
	if len(values) < 2:
		return 0
	mean = _mean(values)
	return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def detect_spikes(series, min_points=6, min_amount=0, window=SPIKE_WINDOW):
	"""Flag unusual full months in `series` (amounts oldest first, current month excluded).

	Only the last `window` months are judged; earlier values are history for the
	three-month average and the same month last year (`series[i - 12]`). A month is a
	spike when it is above `min_amount` and either
	- above mean + 2σ of the other months in the judged window, or
	- above 1.5 × the average of the three months before it.
	Nothing is flagged while the judged window has fewer than `min_points` months with
	activity, so a young company does not get its second month called a peak.

	Returns a list aligned with `series`: None, or
	`{kind: "peak" | "recurring", reasons, value, mean, sigma, avg3, last_year}`.
	`recurring` means the same month last year was within ± 20 %.
	"""
	values = [float(v or 0) for v in series]
	result = [None] * len(values)
	first = max(0, len(values) - window)
	judged = values[first:]
	if sum(1 for v in judged if v) < min_points:
		return result
	for index in range(first, len(values)):
		value = values[index]
		if not value or value < min_amount:
			continue
		others = [v for offset, v in enumerate(judged) if first + offset != index]
		mean = _mean(others)
		sigma = _stdev(others)
		previous3 = values[max(0, index - 3) : index]
		avg3 = _mean(previous3) if len(previous3) == 3 else None
		reasons = []
		if sigma and value > mean + SPIKE_SIGMA * sigma:
			reasons.append("sigma")
		if avg3 and value > SPIKE_AVG3_FACTOR * avg3:
			reasons.append("avg3")
		if not reasons:
			continue
		last_year = values[index - 12] if index >= 12 else None
		recurring = bool(last_year) and abs(value - last_year) <= RECURRING_TOLERANCE * last_year
		result[index] = {
			"kind": "recurring" if recurring else "peak",
			"reasons": reasons,
			"value": value,
			"mean": round(mean, 2),
			"sigma": round(sigma, 2),
			"avg3": round(avg3, 2) if avg3 is not None else None,
			"last_year": last_year,
		}
	return result


def aging_bucket(due_date, today):
	"""Key of AGING_BUCKETS for a receipt due on `due_date`."""
	if not due_date:
		return "none"
	days = (getdate(due_date) - getdate(today)).days
	if days < -30:
		return "overdue_30"
	if days < 0:
		return "overdue"
	if days <= 7:
		return "due_7"
	if days <= 30:
		return "due_30"
	return "later"


def aging_buckets(rows, today, due_field="due_date", amount_field="amount"):
	"""Count and sum rows per AGING_BUCKETS entry; all buckets are returned, in order."""
	result = {key: {"key": key, "label": label, "theme": theme, "value": 0, "amount": 0} for key, label, theme in AGING_BUCKETS}
	for row in rows:
		bucket = result[aging_bucket(row.get(due_field), today)]
		bucket["value"] += 1
		bucket["amount"] = round(bucket["amount"] + (row.get(amount_field) or 0), 2)
	return list(result.values())


def age_summary(dates, today):
	"""Oldest and median age in days of `dates` (None when empty)."""
	today = getdate(today)
	ages = [(today - getdate(value)).days for value in dates if value]
	if not ages:
		return {"oldest_days": None, "median_days": None}
	return {"oldest_days": max(ages), "median_days": percentile(ages, 50)}


def iso_weeks(from_date, to_date):
	"""ISO weeks (Mon–Sun) overlapping [from_date, to_date], each `{key, label, start, end}` (end inclusive)."""
	from_date, to_date = getdate(from_date), getdate(to_date)
	monday = from_date - timedelta(days=from_date.weekday())
	weeks = []
	while monday <= to_date:
		year, week, _day = monday.isocalendar()
		weeks.append({"key": f"{year}-W{week:02d}", "label": f"W{week}", "start": monday, "end": monday + timedelta(days=6)})
		monday += timedelta(days=7)
	return weeks
