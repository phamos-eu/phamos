# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Lead overview of the Sales Cockpit: how many new leads, compared with what (phamos/phamos#1758).

Counts every Lead by ``creation``, disabled and Do Not Contact ones included: a lead that came in, came in. Each
figure carries the filters that reproduce it in ``sales_leads.get_leads``, so a card's number and the list it
opens always agree. The arithmetic is the pure ``build_overview(rows, today)``; the endpoint only fetches rows.
"""

import calendar
from collections import Counter
from datetime import date, timedelta

import frappe
from frappe import _
from frappe.utils import getdate

from phamos.marketing.defaults import LEAD_DIRECTION_FIELD, LEAD_DIRECTIONS

NOT_SET = "none"
DIRECTION_FILTERS = (*LEAD_DIRECTIONS, NOT_SET)
TREND_WINDOWS = (1, 3, 6)
CHART_MONTHS = 24
AVERAGE_MONTHS = 12
# Within this many leads, or this share of the reference, a figure is "on par": at 5-10 leads a month,
# +100% can mean one lead more.
PAR_LEADS = 1
PAR_SHARE = 0.10


@frappe.whitelist()
def get_lead_overview(direction=None):
	from phamos.api.sales_leads import _check_lead_access

	_check_lead_access()
	direction = validate_direction(direction)
	filters = {}
	if direction:
		filters[LEAD_DIRECTION_FIELD] = ["is", "not set"] if direction == NOT_SET else direction
	# get_list, not get_all: User Permissions must narrow the figures just as they narrow the list.
	rows = frappe.get_list(
		"Lead",
		filters=filters,
		fields=["creation", "source", "status", LEAD_DIRECTION_FIELD],
		limit_page_length=0,
		order_by="creation asc",
	)
	return build_overview(rows, getdate(), direction=direction)


def validate_direction(direction):
	if not direction:
		return None
	if direction not in DIRECTION_FILTERS:
		frappe.throw(_("Unknown Inbound / Outbound filter: {0}").format(direction))
	return direction


# --- dates -----------------------------------------------------------------------------------------------------


def month_start(day):
	return day.replace(day=1)


def add_months(day, months):
	"""The same day `months` later (or earlier), clamped to the end of a shorter month."""
	index = day.year * 12 + day.month - 1 + months
	year, month = divmod(index, 12)
	month += 1
	return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def month_end(day):
	return add_months(month_start(day), 1) - timedelta(days=1)


def same_day_in(year, month, day):
	"""`day` of that month, or its last day if the month is shorter (29 Feb → 28 Feb)."""
	return date(year, month, min(day, calendar.monthrange(year, month)[1]))


# --- counting -------------------------------------------------------------------------------------------------


def _split(rows):
	counts = Counter(row["direction"] or NOT_SET for row in rows)
	return {"Inbound": counts["Inbound"], "Outbound": counts["Outbound"], NOT_SET: counts[NOT_SET]}


def _matches(row, filters):
	return all((row[key] or NOT_SET) == value for key, value in filters.items())


def _window(rows, start, end, direction=None, **extra):
	"""Leads created from `start` to `end` (both days included) matching `extra` (source, status, direction),
	with the filters that list exactly them in ``get_leads``."""
	match = dict(extra)
	if direction:
		match["direction"] = direction
	matched = [row for row in rows if start <= row["day"] <= end and _matches(row, match)]
	filters = {"created_from": str(start), "created_to": str(end), **match}
	return {"count": len(matched), "split": _split(matched), "from": str(start), "to": str(end), "filters": filters}


def compare(current, reference):
	"""Difference to a reference: leads first, percent second, and whether that is above, on par or below."""
	if reference is None:
		return {"delta": None, "percent": None, "tone": None}
	delta = current - reference
	percent = round(delta / reference * 100) if reference else None
	if abs(delta) <= max(PAR_LEADS, abs(reference) * PAR_SHARE):
		tone = "par"
	else:
		tone = "above" if delta > 0 else "below"
	return {"delta": round(delta, 1), "percent": percent, "tone": tone}


def _normalise(rows):
	out = []
	for row in rows:
		created = row.get("creation")
		if not created:
			continue
		out.append(
			{
				"day": getdate(created),
				"source": row.get("source") or "",
				"status": row.get("status") or "",
				"direction": row.get(LEAD_DIRECTION_FIELD) or "",
			}
		)
	return out


def _by_key(rows, key, start, end, direction, filter_key, empty_label):
	matched = [row for row in rows if start <= row["day"] <= end and _matches(row, {"direction": direction} if direction else {})]
	counts = Counter(row[key] or NOT_SET for row in matched)
	result = []
	for value, _count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
		item = _window(rows, start, end, direction, **{filter_key: value})
		item.update(key=value, label=empty_label if value == NOT_SET else value)
		result.append(item)
	return result


def _changes(rows, current, previous, direction):
	"""Where the difference between two windows comes from: per direction and per source, biggest drop first."""

	def per(key, values, filter_key, empty_label):
		out = []
		for value in values:
			# The direction split runs only without a page-wide direction, so it takes that slot.
			if filter_key == "direction":
				now, before = _window(rows, *current, value), _window(rows, *previous, value)
			else:
				now = _window(rows, *current, direction, **{filter_key: value})
				before = _window(rows, *previous, direction, **{filter_key: value})
			if not now["count"] and not before["count"]:
				continue
			out.append(
				{
					"key": value,
					"label": empty_label if value == NOT_SET else value,
					"current": now["count"],
					"previous": before["count"],
					"delta": now["count"] - before["count"],
					"current_filters": now["filters"],
					"previous_filters": before["filters"],
				}
			)
		return sorted(out, key=lambda item: (item["delta"], item["label"]))

	in_range = [r for r in rows if previous[0] <= r["day"] <= current[1]]
	sources = sorted({r["source"] or NOT_SET for r in in_range})
	directions = [] if direction else list(DIRECTION_FILTERS)
	return {
		"direction": per("direction", directions, "direction", "Not set"),
		"source": per("source", sources, "source", "No source"),
	}


def build_overview(rows, today, direction=None):
	"""All figures of the overview for the leads in `rows` (dicts with creation, source, status, direction)."""
	rows = _normalise(rows)
	today = getdate(today)
	first_day = min((row["day"] for row in rows), default=None)
	this_month = month_start(today)

	def covered(start):
		"""Whether data reaches back to `start`: before the first lead's month, a 0 would be a guess, not a count."""
		return first_day is not None and month_start(first_day) <= start

	# This month so far, and the same days a year earlier.
	current = _window(rows, this_month, today, direction)
	ly_start = add_months(this_month, -12)
	ly_end = same_day_in(ly_start.year, ly_start.month, today.day)
	last_year = _window(rows, ly_start, ly_end, direction)
	last_year["has_data"] = covered(ly_start)
	last_year.update(compare(current["count"], last_year["count"] if last_year["has_data"] else None))

	# Rolling 12-month average, prorated to the days elapsed this month.
	days_elapsed = today.day
	days_in_month = calendar.monthrange(today.year, today.month)[1]
	months = []
	for back in range(AVERAGE_MONTHS, 0, -1):
		start = add_months(this_month, -back)
		if not covered(start):
			continue
		item = _window(rows, start, month_end(start), direction)
		item["key"] = start.strftime("%Y-%m")
		months.append(item)
	average = None
	if months:
		monthly = sum(m["count"] for m in months) / len(months)
		average = {
			"monthly": round(monthly, 1),
			"expected": round(monthly * days_elapsed / days_in_month, 1),
			"months": months,
			"months_used": len(months),
		}
		for item in months:
			item.update(compare(item["count"], monthly))
		average.update(compare(current["count"], average["expected"]))

	# Same day range of this month in every earlier year with data.
	years = []
	for back in range(1, today.year - (first_day.year if first_day else today.year) + 1):
		start = add_months(this_month, -12 * back)
		if not covered(start):
			continue
		item = _window(rows, start, same_day_in(start.year, start.month, today.day), direction)
		full = _window(rows, start, month_end(start), direction)
		item.update(year=start.year, full_count=full["count"], full_filters=full["filters"])
		years.append(item)
	season = None
	if years:
		mean = sum(y["count"] for y in years) / len(years)
		season = {"expected": round(mean, 1), "years": years}
		season.update(compare(current["count"], mean))

	# Trend: the last N complete months against the N before them.
	trends = []
	for n in TREND_WINDOWS:
		cur = (add_months(this_month, -n), this_month - timedelta(days=1))
		prev = (add_months(this_month, -2 * n), cur[0] - timedelta(days=1))
		item = {
			"months": n,
			"current": _window(rows, *cur, direction),
			"previous": _window(rows, *prev, direction),
			"has_data": covered(prev[0]),
		}
		item.update(compare(item["current"]["count"], item["previous"]["count"] if item["has_data"] else None))
		item["changes"] = _changes(rows, cur, prev, direction) if item["has_data"] else None
		trends.append(item)

	# Monthly chart, with the same month a year earlier beside each.
	chart = []
	for back in range(CHART_MONTHS, -1, -1):
		start = add_months(this_month, -back)
		end = today if back == 0 else month_end(start)
		item = _window(rows, start, end, direction)
		before = add_months(start, -12)
		item.update(
			key=start.strftime("%Y-%m"),
			partial=back == 0,
			last_year=_window(rows, before, month_end(before), direction)["count"] if covered(before) else None,
		)
		chart.append(item)

	last3 = (add_months(this_month, -3), this_month - timedelta(days=1))
	by_source = {
		"this_month": _by_key(rows, "source", this_month, today, direction, "source", "No source"),
		"last_3_months": _by_key(rows, "source", *last3, direction, "source", "No source"),
		"last_3_months_range": {"from": str(last3[0]), "to": str(last3[1])},
	}
	by_status = _by_key(rows, "status", this_month, today, direction, "status", "No status")

	not_set = None
	if not direction:
		missing = [row for row in rows if not row["direction"]]
		not_set = {"count": len(missing), "filters": {"direction": NOT_SET}}

	return {
		"today": str(today),
		"direction": direction,
		"first_lead": str(first_day) if first_day else None,
		"days_elapsed": days_elapsed,
		"days_in_month": days_in_month,
		"this_month": current,
		"last_year": last_year,
		"average": average,
		"season": season,
		"trends": trends,
		"chart": chart,
		"by_source": by_source,
		"by_status": by_status,
		"not_set": not_set,
	}
