# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit Overview (#2236): one short summary per page, from the pages' own endpoints; team
totals only, presence without the timer; a tile that fails is missing, the others still load."""

from unittest.mock import patch

import frappe

from phamos.api import team_cockpit as tc
from phamos.cockpits import team_successes
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase


class TestOverview(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.assign(self.anna, TEAM_A, "2020-01-01")
		for patcher in (
			patch("phamos.cockpits.teams.require_active_team", return_value=TEAM_A),
			patch.object(tc, "check_app_permission", return_value=True),
			# the GitLab figures need synced data; their own tests cover them
			patch.object(
				tc,
				"get_gitlab_statistics",
				return_value=frappe._dict(
					windows={"current": frappe._dict(closed_total=7, opened_total=4)},
					merge_requests={"current": frappe._dict(merged_total=3)},
				),
			),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def success(self, team, title, day):
		success = frappe._dict(
			success_type="Kudos", title=title, text="", employee=self.anna, key=f"test:{title}",
			reference_doctype=None, reference_name=None,
		)
		team_successes.record_success(team, success, day=day, post=False)

	def test_every_tile_of_the_active_team(self):
		for i, day in enumerate(["2026-03-01", "2026-03-04", "2026-03-02", "2026-03-03"]):
			self.success(TEAM_A, f"Mine {i}", day)
		self.success(TEAM_B, "Theirs", "2026-03-05")
		data = tc.get_team_overview()
		self.assertEqual(data["team"], TEAM_A)
		# presence only: what a mate works on stays on the Team mates page
		self.assertEqual([m["employee"] for m in data["mates"]], [self.anna])
		self.assertNotIn("timer", data["mates"][0])
		# the three newest of the team, not another team's
		self.assertEqual([s["title"] for s in data["successes"]], ["Mine 1", "Mine 3", "Mine 2"])
		self.assertEqual(data["gitlab"], {"closed": 7, "opened": 4, "merged": 3})
		self.assertEqual(set(data["hours"]), {"logged", "available", "booked_rate", "billable_rate"})
		self.assertIsInstance(data["appointments"], list)
		self.assertEqual(set(data["absences"]), {"absences", "holidays"})
		self.assertEqual(data["attention"]["count"], 0)

	def test_figures_are_cached_per_team(self):
		frappe.cache.delete_keys("team_overview:")
		self.addCleanup(frappe.cache.delete_keys, "team_overview:")
		tc.get_team_overview()
		with patch.object(tc, "get_gitlab_statistics", side_effect=AssertionError("not cached")):
			self.assertEqual(tc.get_team_overview()["gitlab"], {"closed": 7, "opened": 4, "merged": 3})

	def test_at_most_three_records_need_attention(self):
		for _i in range(5):
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Idle", "custom_team": TEAM_A}).insert(ignore_permissions=True)
			frappe.db.set_value("Issue", doc.name, "modified", "2020-01-01 09:00:00", update_modified=False)
		frappe.db.set_single_value("Cockpit Settings", "team_attention_idle_days", 10)
		attention = tc.get_team_overview()["attention"]
		self.assertEqual(attention["count"], 5)
		self.assertEqual(len(attention["items"]), 3)
		# records only: the assignees stay on the Needs attention page
		self.assertNotIn("assignees", attention["items"][0])

	def test_a_failing_tile_leaves_the_others(self):
		frappe.cache.delete_keys("team_overview:")
		self.addCleanup(frappe.cache.delete_keys, "team_overview:")
		with patch.object(tc, "get_gitlab_statistics", side_effect=RuntimeError("no sync")), patch.object(
			frappe, "log_error"
		) as log:
			data = tc.get_team_overview()
		self.assertIsNone(data["gitlab"])
		self.assertIsNotNone(data["hours"])
		self.assertEqual(log.call_count, 1)

	def test_without_issue_rights_the_attention_tile_is_missing(self):
		real = frappe.has_permission
		with patch.object(frappe, "has_permission", side_effect=lambda doctype, *a, **k: doctype != "Issue" and real(doctype, *a, **k)), patch.object(
			frappe, "log_error"
		) as log:
			data = tc.get_team_overview()
		self.assertIsNone(data["attention"])
		log.assert_not_called()

	def test_only_for_cockpit_users(self):
		tc.check_app_permission.return_value = False
		with self.assertRaises(frappe.PermissionError):
			tc.get_team_overview()
