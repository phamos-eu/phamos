# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Implementation Baseline (#1971): the plan both sides agreed in a planning session.

A snapshot of the implementation's chapters and features, made when a Stakeholder Meeting of
type Planning is submitted. One baseline is current per implementation; earlier ones stay for
history. `get_baseline_variance` compares today's plan with the current baseline and feeds the
roadmap and the PM triangle (#1694, #1681). Releases (#1986) are in the snapshot with their
target date and ranked features.
"""

import json

import frappe
from frappe.model.document import Document
from frappe.utils import date_diff, getdate, today

CHAPTER_FIELDS = ("chapter_title", "status", "planned_start", "target_date", "current_level", "target_level")
FEATURE_FIELDS = ("title", "status", "priority", "planned_start", "target_date", "target_level", "estimated_hours")


class ImplementationBaseline(Document):
	pass


def create_baseline(implementation, stakeholder_meeting=None, baseline_date=None):
	"""Snapshot the implementation's plan and make it the current baseline."""
	baseline = frappe.get_doc(
		{
			"doctype": "Implementation Baseline",
			"implementation": implementation,
			"stakeholder_meeting": stakeholder_meeting,
			"baseline_date": baseline_date or today(),
			"is_current": 1,
		}
	)
	for chapter in frappe.get_all(
		"Implementation Chapter",
		filters={"implementation": implementation},
		fields=["name", *CHAPTER_FIELDS],
		order_by="planned_start asc, name asc",
	):
		baseline.append("chapters", {"chapter": chapter.pop("name"), **chapter})
	for feature in frappe.get_all(
		"Implementation Feature",
		filters={"implementation": implementation},
		fields=["name", *FEATURE_FIELDS],
		order_by="planned_start asc, name asc",
	):
		baseline.append("features", {"feature": feature.pop("name"), **feature})
	for release in frappe.get_all(
		"Implementation Release",
		filters={"implementation": implementation, "status": ["!=", "Cancelled"]},
		fields=["name", "title", "status", "target_date"],
		order_by="target_date asc, name asc",
	):
		name = release.pop("name")
		baseline.append("releases", {"release": name, "ranking": json.dumps(_ranking(name)), **release})
	frappe.db.set_value(
		"Implementation Baseline", {"implementation": implementation, "is_current": 1}, "is_current", 0
	)
	baseline.insert(ignore_permissions=True)
	return baseline


@frappe.whitelist()
def get_baseline_variance(implementation):
	"""Date and scope differences of today's plan against the current baseline.

	Returns None without a baseline. Shifts are in days, positive = later than agreed.
	"""
	frappe.has_permission("Implementation", "read", doc=implementation, throw=True)
	name = frappe.db.get_value("Implementation Baseline", {"implementation": implementation, "is_current": 1})
	if not name:
		return None
	baseline = frappe.get_doc("Implementation Baseline", name)

	chapters_now = {
		row.name: row
		for row in frappe.get_all(
			"Implementation Chapter", filters={"implementation": implementation}, fields=["name", *CHAPTER_FIELDS]
		)
	}
	features_now = {
		row.name: row
		for row in frappe.get_all(
			"Implementation Feature", filters={"implementation": implementation}, fields=["name", *FEATURE_FIELDS]
		)
	}

	releases_now = {
		row.name: row
		for row in frappe.get_all(
			"Implementation Release",
			filters={"implementation": implementation},
			fields=["name", "title", "status", "target_date"],
		)
	}

	in_baseline = {row.feature for row in baseline.features}
	dropped_before = {row.feature for row in baseline.features if row.status == "Dropped"}
	return {
		"baseline": baseline.name,
		"baseline_date": baseline.baseline_date,
		"stakeholder_meeting": baseline.stakeholder_meeting,
		"chapters": [
			_row_variance(row.chapter, row.chapter_title, row, chapters_now.get(row.chapter), "chapter_title")
			for row in baseline.chapters
		],
		"features": [
			_row_variance(row.feature, row.title, row, features_now.get(row.feature), "title")
			for row in baseline.features
		],
		"releases": [_release_variance(row, releases_now.get(row.release)) for row in baseline.releases],
		"scope": {
			"added": [
				{"name": name, "title": row.title}
				for name, row in features_now.items()
				if name not in in_baseline and row.status != "Dropped"
			],
			"dropped": [
				{"name": row.feature, "title": row.title}
				for row in baseline.features
				if row.feature not in dropped_before
				and (row.feature not in features_now or features_now[row.feature].status == "Dropped")
			],
		},
	}


def _row_variance(name, title, then, now, title_field):
	if not now:
		return {"name": name, "title": title, "removed": True}
	return {
		"name": name,
		"title": now.get(title_field) or title,
		"start_shift_days": _shift(then.planned_start, now.planned_start),
		"target_shift_days": _shift(then.target_date, now.target_date),
		"status_then": then.status,
		"status_now": now.status,
		"target_level_then": then.target_level,
		"target_level_now": now.target_level,
	}


def _shift(then, now):
	if not then or not now:
		return None
	return date_diff(getdate(now), getdate(then))


def _ranking(release):
	return frappe.get_all(
		"Implementation Release Feature",
		filters={"parent": release, "parenttype": "Implementation Release"},
		pluck="feature",
		order_by="idx asc",
	)


def _release_variance(then, now):
	if not now:
		return {"name": then.release, "title": then.title, "removed": True}
	ranking_then, ranking_now = json.loads(then.ranking or "[]"), _ranking(now.name)
	return {
		"name": now.name,
		"title": now.title,
		"target_shift_days": _shift(then.target_date, now.target_date),
		"status_then": then.status,
		"status_now": now.status,
		"features_added": [name for name in ranking_now if name not in ranking_then],
		"features_removed": [name for name in ranking_then if name not in ranking_now],
		"reranked": [name for name in ranking_now if name in ranking_then]
		!= [name for name in ranking_then if name in ranking_now],
	}
