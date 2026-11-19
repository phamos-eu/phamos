# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Implementation Release (#1986): plan a release with the customer before a tag exists.

A release has a target date, a ranked list of features and the GitLab milestones that ship
them. The realistic check compares the open effort with the team capacity until the target
date, so both sides see early what fits:

- Effort of a feature: its estimated hours; once its GitLab issues carry time estimates (#1985),
  the open estimate of those issues (estimate minus time spent, closed issues count 0).
- Capacity: the weekly capacity of the Implementation's team members from today to the target
  date, without weekends, holidays and approved leave, times the agreed team capacity share.
- Overlapping releases share the capacity in date order, features in rank order. A feature
  "fits" while the running effort stays within the capacity until its release's date: the
  cut line.

When GitLab publishes a release with this release's milestones, it is linked and set Released
(`link_published_release`). Its features are not set Live: the PM confirms each one against
its definition of done. Triage with consent (re-rank, move, new date) follows with #1971.
"""

from datetime import timedelta

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, today

ACTIVE = ("Planned", "In Progress")
DONE_FEATURE_STATUSES = ("Live", "Dropped")
WORKDAYS_PER_WEEK = 5
AMBER_BUFFER = 0.2  # amber when less than 20% of the capacity is left


class ImplementationRelease(Document):
	def validate(self):
		for index, row in enumerate(self.features, start=1):
			row.rank = index
		self.validate_links()
		self.warn_about_missing_milestones()
		if self.status in ACTIVE:
			self.apply_check(compute_release_check(self.implementation, current=self).get(self.name or "__new__"))
		else:
			self.apply_check(None)

	def on_update(self):
		# the releases after this one share what is left of the capacity
		refresh_release_check(self.implementation, skip=self.name)

	def after_delete(self):
		# the row is gone now, in the same transaction: the other releases get its capacity back
		refresh_release_check(self.implementation)

	def validate_links(self):
		if self.chapter and frappe.db.get_value("Implementation Chapter", self.chapter, "implementation") != self.implementation:
			frappe.throw(_("Chapter {0} belongs to another implementation.").format(self.chapter))
		seen = set()
		names = [row.feature for row in self.features]
		owners = dict(
			frappe.get_all(
				"Implementation Feature", filters={"name": ["in", names or [""]]}, fields=["name", "implementation"], as_list=True
			)
		)
		# only an active release claims its features; a released one keeps its history even when a
		# feature that is not Live yet is planned again in a new release
		elsewhere = self._features_in_other_releases(names) if self.status in ACTIVE else {}
		for row in self.features:
			if row.feature in seen:
				frappe.throw(_("Feature {0} is listed twice.").format(row.feature))
			seen.add(row.feature)
			if owners.get(row.feature) != self.implementation:
				frappe.throw(_("Feature {0} belongs to another implementation.").format(row.feature))
			if row.feature in elsewhere:
				frappe.throw(
					_("Feature {0} is already planned in release {1}. Move it from there.").format(
						row.feature, elsewhere[row.feature]
					)
				)

	def _features_in_other_releases(self, names):
		if not names:
			return {}
		release = frappe.qb.DocType("Implementation Release")
		row = frappe.qb.DocType("Implementation Release Feature")
		return dict(
			frappe.qb.from_(row)
			.join(release)
			.on(row.parent == release.name)
			.select(row.feature, release.name)
			.where(row.parenttype == "Implementation Release")
			.where(row.feature.isin(names))
			.where(release.name != (self.name or ""))
			.where(release.implementation == self.implementation)
			.where(release.status.isin(ACTIVE))
			.run()
		)

	def warn_about_missing_milestones(self):
		"""A feature's GitLab milestone belongs in the release, so both lists stay in step."""
		names = [row.feature for row in self.features]
		if not names:
			return
		included = {row.gitlab_milestone for row in self.milestones}
		missing = sorted(
			{
				milestone
				for milestone in frappe.get_all(
					"Implementation Feature",
					filters={"name": ["in", names], "gitlab_milestone": ["is", "set"]},
					pluck="gitlab_milestone",
				)
				if milestone not in included
			}
		)
		if missing:
			frappe.msgprint(
				_("These milestones of its features are not in the release: {0}").format(", ".join(missing)),
				indicator="orange",
				alert=True,
			)

	def apply_check(self, check):
		if not check:
			self.fit = self.effort_hours = self.capacity_hours = None
			for row in self.features:
				row.effort_hours = row.fits = None
			return
		self.fit, self.effort_hours, self.capacity_hours = check["fit"], check["effort_hours"], check["capacity_hours"]
		for row in self.features:
			row.effort_hours, row.fits = check["features"].get(row.feature, (0, 0))


# Effort and capacity ---------------------------------------------------------------------------


def feature_efforts(features):
	"""Open effort in hours per feature name, for rows with name, status and estimated_hours."""
	names = [feature.name for feature in features]
	issues = {}
	for issue in frappe.get_all(
		"GitLab Issue",
		filters={"implementation_feature": ["in", names or [""]]},
		fields=["implementation_feature", "state", "time_estimate_hours", "time_spent_hours"],
	):
		issues.setdefault(issue.implementation_feature, []).append(issue)
	efforts = {}
	for feature in features:
		linked = issues.get(feature.name, [])
		if feature.status in DONE_FEATURE_STATUSES:
			efforts[feature.name] = 0.0
		elif any(flt(issue.time_estimate_hours) for issue in linked):
			# GitLab estimates refine the feature's hours but never make it look smaller than they
			# do: while only some issues are estimated, what is left of the feature's own hours wins
			open_estimates = sum(
				max(flt(issue.time_estimate_hours) - flt(issue.time_spent_hours), 0)
				for issue in linked
				if issue.state != "closed"
			)
			left_of_hours = flt(feature.estimated_hours) - sum(flt(issue.time_spent_hours) for issue in linked)
			efforts[feature.name] = max(open_estimates, left_of_hours, 0.0)
		else:
			efforts[feature.name] = flt(feature.estimated_hours)
	return efforts


def team_capacity(implementation, start, end):
	"""Hours the Implementation's team can give it between `start` and `end` (inclusive)."""
	from phamos.cockpits.workdays import days_off

	start, end = getdate(start), getdate(end)
	if end < start:
		return 0.0
	team, share = frappe.db.get_value("Implementation", implementation, ["team", "team_capacity_share"])
	if not team:
		return 0.0
	hours = 0.0
	for member in frappe.get_all(
		"Team Members", filters={"parent": team, "parenttype": "Team"}, fields=["employee", "weekly_capacity"]
	):
		if not member.weekly_capacity:
			continue
		user = frappe.db.get_value("Employee", member.employee, "user_id")
		off = days_off(user, start, end) if user else set()
		day, workdays = start, 0
		while day <= end:
			if day.weekday() < WORKDAYS_PER_WEEK and day not in off:
				workdays += 1
			day += timedelta(days=1)
		hours += flt(member.weekly_capacity) / WORKDAYS_PER_WEEK * workdays
	# no agreed share yet: the whole team, so the check never looks better than it is
	return round(hours * (flt(share) / 100 if flt(share) else 1), 1)


def compute_release_check(implementation, current=None):
	"""The realistic check of every active release, keyed by release name ("__new__" for an unsaved one).

	`current` is a release being saved: its unsaved rows and date replace the stored ones.
	"""
	releases = {
		row.name: frappe._dict(row, features=None)
		for row in frappe.get_all(
			"Implementation Release",
			filters={"implementation": implementation, "status": ["in", ACTIVE]},
			fields=["name", "target_date"],
		)
	}
	if current is not None:
		key = current.name or "__new__"
		releases.pop(key, None)
		if current.status in ACTIVE:
			releases[key] = frappe._dict(
				name=key, target_date=current.target_date, features=[row.feature for row in current.features]
			)
	stored = [name for name, release in releases.items() if release.features is None]
	rows = frappe.get_all(
		"Implementation Release Feature",
		filters={"parent": ["in", stored or [""]], "parenttype": "Implementation Release"},
		fields=["parent", "feature"],
		order_by="idx asc",
	)
	for release in releases.values():
		if release.features is None:
			release.features = [row.feature for row in rows if row.parent == release.name]

	all_features = [name for release in releases.values() for name in release.features]
	efforts = feature_efforts(
		frappe.get_all(
			"Implementation Feature",
			filters={"name": ["in", all_features or [""]]},
			fields=["name", "status", "estimated_hours"],
		)
	)

	start, running, result = getdate(today()), 0.0, {}
	for release in sorted(releases.values(), key=lambda r: (getdate(r.target_date), r.name)):
		capacity_until = team_capacity(implementation, start, release.target_date)
		available = max(capacity_until - running, 0)
		effort, all_fit, features = 0.0, True, {}
		for name in release.features:
			hours = round(efforts.get(name, 0.0), 1)
			running += hours
			effort += hours
			fits = running <= capacity_until
			all_fit = all_fit and fits
			features[name] = (hours, 1 if fits else 0)
		if not all_fit:
			fit = "Red"
		elif effort > available * (1 - AMBER_BUFFER):
			fit = "Amber"
		else:
			fit = "Green"
		result[release.name] = {
			"fit": fit,
			"effort_hours": round(effort, 1),
			"capacity_hours": round(available, 1),
			"features": features,
		}
	return result


def refresh_release_check(implementation, skip=None):
	"""Write the current check to the stored active releases (except `skip`, which just saved)."""
	for name, check in compute_release_check(implementation).items():
		if name == skip:
			continue
		frappe.db.set_value(
			"Implementation Release",
			name,
			{"fit": check["fit"], "effort_hours": check["effort_hours"], "capacity_hours": check["capacity_hours"]},
			update_modified=False,
		)
		for row in frappe.get_all(
			"Implementation Release Feature", filters={"parent": name, "parenttype": "Implementation Release"}, fields=["name", "feature"]
		):
			hours, fits = check["features"].get(row.feature, (0, 0))
			frappe.db.set_value(
				"Implementation Release Feature", row.name, {"effort_hours": hours, "fits": fits}, update_modified=False
			)


def refresh_all_release_checks():
	"""Daily: capacity shrinks with every day that passes, and leave changes."""
	for implementation in frappe.get_all(
		"Implementation Release", filters={"status": ["in", ACTIVE]}, pluck="implementation", distinct=True
	):
		# one implementation with broken team or holiday data must not leave the others stale
		frappe.db.savepoint("release_check_refresh")
		try:
			refresh_release_check(implementation)
		except Exception:
			frappe.db.rollback(save_point="release_check_refresh")
			frappe.log_error(frappe.get_traceback(), f"Implementation Release Check Error - {implementation}")


@frappe.whitelist()
def get_release_check(implementation):
	"""The realistic check of the implementation's active releases, for the cockpit and the roadmap."""
	frappe.has_permission("Implementation", "read", doc=implementation, throw=True)
	return compute_release_check(implementation)


# GitLab ----------------------------------------------------------------------------------------


def link_published_release(doc, method=None):
	"""on_update of GitLab Release: a published release (not upcoming) that ships all the milestones
	of a planned release is linked to it, and the planned release becomes Released. A release that
	ships only part of them leaves the planned release as it is. Its features stay as they are until
	the PM confirms them Live."""
	if doc.upcoming or not doc.released_at or not doc.milestones:
		return
	implementation = frappe.db.get_value("GitLab Project", doc.gitlab_project, "implementation")
	if not implementation:
		return
	shipped = {row.gitlab_milestone for row in doc.milestones}
	planned = {}
	for row in frappe.get_all(
		"Implementation Release Milestone",
		filters={
			"parent": ["in", frappe.get_all(
				"Implementation Release Milestone",
				filters={"gitlab_milestone": ["in", list(shipped)], "parenttype": "Implementation Release"},
				pluck="parent",
				distinct=True,
			) or [""]],
			"parenttype": "Implementation Release",
		},
		fields=["parent", "gitlab_milestone"],
	):
		planned.setdefault(row.parent, set()).add(row.gitlab_milestone)
	parents = [name for name, milestones in planned.items() if milestones <= shipped]
	for name in frappe.get_all(
		"Implementation Release",
		filters={
			"name": ["in", parents or [""]],
			"implementation": implementation,
			"status": ["in", ACTIVE],
			"gitlab_release": ["is", "not set"],
		},
		pluck="name",
	):
		# a planned release that no longer validates must not stop the GitLab Release from syncing
		frappe.db.savepoint("implementation_release_link")
		try:
			release = frappe.get_doc("Implementation Release", name)
			release.gitlab_release = doc.name
			release.status = "Released"
			release.save(ignore_permissions=True)
		except Exception:
			frappe.db.rollback(save_point="implementation_release_link")
			frappe.log_error(frappe.get_traceback(), f"Implementation Release Link Error - {name}")


@frappe.whitelist()
def get_released_features_awaiting_live(implementation):
	"""Features of released releases that the PM has not yet confirmed Live: a to-do for the PM."""
	frappe.has_permission("Implementation", "read", doc=implementation, throw=True)
	released = frappe.get_all(
		"Implementation Release", filters={"implementation": implementation, "status": "Released"}, pluck="name"
	)
	features = frappe.get_all(
		"Implementation Release Feature",
		filters={"parent": ["in", released or [""]], "parenttype": "Implementation Release"},
		fields=["feature", "parent"],
	)
	statuses = dict(
		frappe.get_all(
			"Implementation Feature",
			filters={"name": ["in", [row.feature for row in features] or [""]]},
			fields=["name", "status"],
			as_list=True,
		)
	)
	# "release" is a reserved word in MariaDB, so the alias is made here
	return [
		{"feature": row.feature, "release": row.parent}
		for row in features
		if statuses.get(row.feature) not in DONE_FEATURE_STATUSES
	]
