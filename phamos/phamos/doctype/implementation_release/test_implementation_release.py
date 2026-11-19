# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Release planning: effort, capacity, the cut line and the link to GitLab releases (#1986)."""

import random
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.implementation_release import implementation_release
from phamos.phamos.doctype.implementation_release.implementation_release import (
	feature_efforts,
	get_released_features_awaiting_live,
	team_capacity,
)
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation

NEAR, FAR = add_days(today(), 30), add_days(today(), 60)


def make_release(implementation, features=(), target_date=NEAR, milestones=(), **values):
	return frappe.get_doc(
		{
			"doctype": "Implementation Release",
			"title": values.pop("title", "Go-live"),
			"implementation": implementation,
			"target_date": target_date,
			"features": [{"feature": name} for name in features],
			"milestones": [{"gitlab_milestone": name} for name in milestones],
			**values,
		}
	).insert(ignore_permissions=True)


def gitlab_issue(feature, state="opened", estimate=0, spent=0):
	frappe.get_doc(
		{
			"doctype": "GitLab Issue",
			"name": f"_Test REL {frappe.generate_hash(length=8)}",
			"issue_id": str(random.randint(10**8, 10**9)),
			"title": "work",
			"state": state,
			"implementation_feature": feature,
			"time_estimate_hours": estimate,
			"time_spent_hours": spent,
		}
	).db_insert()


def fixed_capacity(by_date):
	"""team_capacity replaced by fixed hours per target date."""
	return mock.patch.object(
		implementation_release, "team_capacity", side_effect=lambda impl, start, end: by_date[str(getdate(end))]
	)


class TestImplementationRelease(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation().name

	def test_effort_from_hours_then_from_gitlab_estimates(self):
		feature = make_feature(self.implementation, title="Hours", estimated_hours=12)
		live = make_feature(self.implementation, title="Done", estimated_hours=8, status="Live")
		rows = frappe.get_all(
			"Implementation Feature", filters={"name": ["in", [feature.name, live.name]]}, fields=["name", "status", "estimated_hours"]
		)
		self.assertEqual(feature_efforts(rows), {feature.name: 12.0, live.name: 0.0})

		gitlab_issue(feature.name, estimate=5, spent=2)
		gitlab_issue(feature.name, estimate=4, spent=6)  # overspent counts 0, never negative
		gitlab_issue(feature.name, state="closed", estimate=10)
		# open estimates 3 h, but 12 h - 8 h spent leaves 4 h: partly estimated issues never shrink it
		self.assertEqual(feature_efforts(rows)[feature.name], 4.0)
		gitlab_issue(feature.name, estimate=20)
		self.assertEqual(feature_efforts(rows)[feature.name], 23.0)  # estimates above the hours win

	def test_capacity_with_leave_and_share(self):
		user = f"rel-{frappe.generate_hash(length=6)}@example.com"
		frappe.get_doc({"doctype": "User", "email": user, "first_name": "Rel", "send_welcome_email": 0}).insert(
			ignore_permissions=True
		)
		full, part = (f"_T-REL-{frappe.generate_hash(length=6)}" for _ in range(2))
		for name, user_id in ((full, user), (part, None)):
			frappe.get_doc(
				{"doctype": "Employee", "name": name, "first_name": name, "status": "Active", "user_id": user_id}
			).db_insert()
		team = f"_Test REL Team {frappe.generate_hash(length=6)}"
		frappe.get_doc({"doctype": "Team", "name": team, "team_name": team}).db_insert()
		for idx, (employee, weekly) in enumerate(((full, 40), (part, 20)), start=1):
			frappe.get_doc(
				{
					"doctype": "Team Members",
					"parent": team,
					"parenttype": "Team",
					"parentfield": "team_members",
					"idx": idx,
					"employee": employee,
					"weekly_capacity": weekly,
				}
			).db_insert()
		frappe.db.set_value("Implementation", self.implementation, {"team": team, "team_capacity_share": 50})
		monday, friday = "2030-01-07", "2030-01-11"
		with mock.patch("phamos.cockpits.workdays._holiday_list", return_value=None):
			self.assertEqual(team_capacity(self.implementation, monday, friday), 30.0)  # (8 + 4) × 5 × 50%
			frappe.get_doc(
				{
					"doctype": "Leave Application",
					"name": f"_T-REL-LA-{frappe.generate_hash(length=6)}",
					"employee": full,
					"from_date": "2030-01-08",
					"to_date": "2030-01-09",
					"status": "Approved",
					"docstatus": 1,
				}
			).db_insert()
			self.assertEqual(team_capacity(self.implementation, monday, friday), 22.0)  # (8 × 3 + 4 × 5) × 50%
		self.assertEqual(team_capacity(self.implementation, friday, monday), 0.0)

	def test_cut_line_across_two_overlapping_releases(self):
		a, b, c, d = (
			make_feature(self.implementation, title=title, estimated_hours=hours)
			for title, hours in (("A", 6), ("B", 6), ("C", 10), ("D", 10))
		)
		with fixed_capacity({str(getdate(NEAR)): 10, str(getdate(FAR)): 25}):
			first = make_release(self.implementation, [a.name, b.name], NEAR, title="First")
			second = make_release(self.implementation, [c.name, d.name], FAR, title="Second")
		first.reload()
		second.reload()
		# first: 6 fits, 12 > 10 does not
		self.assertEqual([(row.rank, row.fits) for row in first.features], [(1, 1), (2, 0)])
		self.assertEqual((first.fit, first.effort_hours, first.capacity_hours), ("Red", 12, 10))
		# second shares what is left: 22 fits into 25, 32 does not
		self.assertEqual([row.fits for row in second.features], [1, 0])
		self.assertEqual(second.capacity_hours, 13)

		# taking A out of the first release moves both cut lines
		with fixed_capacity({str(getdate(NEAR)): 10, str(getdate(FAR)): 25}):
			first.remove(first.features[0])
			first.save()
		second.reload()
		self.assertEqual((first.fit, first.effort_hours, first.features[0].rank), ("Green", 6, 1))
		self.assertEqual((second.capacity_hours, [row.fits for row in second.features]), (19, [1, 0]))
		self.assertEqual(second.fit, "Red")

	def test_a_feature_is_planned_in_one_release_only(self):
		feature = make_feature(self.implementation, estimated_hours=1)
		with fixed_capacity({str(getdate(NEAR)): 100, str(getdate(FAR)): 100}):
			make_release(self.implementation, [feature.name], NEAR)
			self.assertRaises(frappe.ValidationError, make_release, self.implementation, [feature.name], FAR)
			other = make_feature(make_implementation().name, title="Elsewhere")
			self.assertRaises(frappe.ValidationError, make_release, self.implementation, [other.name], FAR)

	def test_milestone_of_a_feature_missing_in_the_release_warns(self):
		milestone = frappe.new_doc("GitLab Milestones")
		milestone.update({"title": "Sprint", "milestone_id": random.randint(10**8, 10**9)})
		milestone.insert(ignore_permissions=True)
		feature = make_feature(self.implementation, gitlab_milestone=milestone.name, estimated_hours=1)
		frappe.message_log = []
		with fixed_capacity({str(getdate(NEAR)): 100}):
			make_release(self.implementation, [feature.name], NEAR)
		self.assertTrue(any("not in the release" in str(message) for message in frappe.message_log))

	def test_published_gitlab_release_sets_released_and_leaves_features(self):
		project = str(random.randint(10**8, 10**9))
		frappe.get_doc(
			{"doctype": "GitLab Project", "project_id": project, "title": "_Test REL", "implementation": self.implementation}
		).insert(ignore_permissions=True)
		milestone = frappe.new_doc("GitLab Milestones")
		milestone.update({"title": "Sprint", "milestone_id": random.randint(10**8, 10**9), "gitlab_project": project})
		milestone.insert(ignore_permissions=True)
		feature = make_feature(self.implementation, status="In Testing", estimated_hours=1, gitlab_milestone=milestone.name)
		with fixed_capacity({str(getdate(NEAR)): 100}):
			release = make_release(self.implementation, [feature.name], NEAR, milestones=[milestone.name])

		def gitlab_release(tag, upcoming):
			return frappe.get_doc(
				{
					"doctype": "GitLab Release",
					"gitlab_project": project,
					"tag_name": tag,
					"title": tag,
					"released_at": "2026-11-20 10:00:00",
					"upcoming": upcoming,
					"milestones": [{"gitlab_milestone": milestone.name}],
				}
			).insert(ignore_permissions=True)

		gitlab_release("v0.9", upcoming=1)
		self.assertEqual(frappe.db.get_value("Implementation Release", release.name, "status"), "Planned")
		published = gitlab_release("v1.0", upcoming=0)
		release.reload()
		self.assertEqual((release.status, release.gitlab_release), ("Released", published.name))
		self.assertEqual(frappe.db.get_value("Implementation Feature", feature.name, "status"), "In Testing")
		self.assertEqual(
			get_released_features_awaiting_live(self.implementation), [{"feature": feature.name, "release": release.name}]
		)


	def test_deleting_a_release_frees_capacity_for_the_next(self):
		a, b = (make_feature(self.implementation, title=t, estimated_hours=h) for t, h in (("A", 8), ("B", 9)))
		with fixed_capacity({str(getdate(NEAR)): 10, str(getdate(FAR)): 10}):
			first = make_release(self.implementation, [a.name], NEAR, title="First")
			second = make_release(self.implementation, [b.name], FAR, title="Second")
			self.assertEqual(frappe.db.get_value("Implementation Release", second.name, "fit"), "Red")
			first.delete()
		self.assertEqual(frappe.db.get_value("Implementation Release", second.name, "fit"), "Amber")

	def test_a_planned_release_that_fails_does_not_stop_the_gitlab_sync(self):
		project = str(random.randint(10**8, 10**9))
		frappe.get_doc(
			{"doctype": "GitLab Project", "project_id": project, "title": "_Test REL", "implementation": self.implementation}
		).insert(ignore_permissions=True)
		milestone = frappe.new_doc("GitLab Milestones")
		milestone.update({"title": "Sprint", "milestone_id": random.randint(10**8, 10**9), "gitlab_project": project})
		milestone.insert(ignore_permissions=True)
		with fixed_capacity({str(getdate(NEAR)): 100}):
			release = make_release(self.implementation, [], NEAR, milestones=[milestone.name])
		with mock.patch.object(
			implementation_release.ImplementationRelease, "validate", side_effect=frappe.ValidationError("broken")
		), mock.patch.object(frappe, "log_error") as log_error:
			published = frappe.get_doc(
				{
					"doctype": "GitLab Release",
					"gitlab_project": project,
					"tag_name": "v2.0",
					"title": "v2.0",
					"released_at": "2026-11-20 10:00:00",
					"upcoming": 0,
					"milestones": [{"gitlab_milestone": milestone.name}],
				}
			).insert(ignore_permissions=True)
		self.assertTrue(frappe.db.exists("GitLab Release", published.name))
		self.assertEqual(frappe.db.get_value("Implementation Release", release.name, "status"), "Planned")
		log_error.assert_called_once()

	def test_a_released_release_keeps_its_features(self):
		feature = make_feature(self.implementation, estimated_hours=1, status="In Testing")
		with fixed_capacity({str(getdate(NEAR)): 100, str(getdate(FAR)): 100}):
			old = make_release(self.implementation, [feature.name], NEAR, title="Shipped")
			frappe.db.set_value("Implementation Release", old.name, "status", "Released")
			make_release(self.implementation, [feature.name], FAR, title="Again")
			old.reload()
			old.features[0].note = "still saveable"
			old.save()

	def test_a_partial_gitlab_release_does_not_release_the_plan(self):
		project = str(random.randint(10**8, 10**9))
		frappe.get_doc(
			{"doctype": "GitLab Project", "project_id": project, "title": "_Test REL", "implementation": self.implementation}
		).insert(ignore_permissions=True)
		one, two = [], []
		for bucket in (one, two):
			milestone = frappe.new_doc("GitLab Milestones")
			milestone.update({"title": "Sprint", "milestone_id": random.randint(10**8, 10**9), "gitlab_project": project})
			milestone.insert(ignore_permissions=True)
			bucket.append(milestone.name)
		with fixed_capacity({str(getdate(NEAR)): 100}):
			release = make_release(self.implementation, [], NEAR, milestones=one + two)
		frappe.get_doc(
			{
				"doctype": "GitLab Release",
				"gitlab_project": project,
				"tag_name": "v0.5",
				"title": "v0.5",
				"released_at": "2026-11-20 10:00:00",
				"upcoming": 0,
				"milestones": [{"gitlab_milestone": one[0]}],
			}
		).insert(ignore_permissions=True)
		self.assertEqual(frappe.db.get_value("Implementation Release", release.name, "status"), "Planned")

	def test_one_broken_implementation_does_not_stop_the_daily_refresh(self):
		other = make_implementation().name
		a = make_feature(self.implementation, estimated_hours=1)
		b = make_feature(other, estimated_hours=1)
		with fixed_capacity({str(getdate(NEAR)): 100}):
			make_release(self.implementation, [a.name], NEAR)
			make_release(other, [b.name], NEAR)
		calls = []

		def refresh(implementation, skip=None):
			calls.append(implementation)
			if implementation == self.implementation:
				raise frappe.ValidationError("broken team")

		with mock.patch.object(implementation_release, "refresh_release_check", side_effect=refresh), mock.patch.object(
			frappe, "log_error"
		) as log_error:
			implementation_release.refresh_all_release_checks()
		self.assertIn(other, calls)
		log_error.assert_called_once()
