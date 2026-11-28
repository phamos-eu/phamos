# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team successes (#1981): the daily rules, each once; kudos and customer praise."""

from datetime import date, datetime
from unittest.mock import patch

import frappe

from phamos.cockpits import team_successes as ts
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase

TODAY = date(2026, 3, 18)
OWN = "_Test Success Own Project"


class SuccessTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.assign(self.anna, TEAM_A, "2025-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2025-01-01")
		self.assign(self.cara, TEAM_B, "2025-01-01")
		self.users = {e: frappe.db.get_value("Employee", e, "user_id") for e in (self.anna, self.ben, self.cara)}
		posted = patch.object(ts, "_post_in_team_chat")
		self.posted = posted.start()
		self.addCleanup(posted.stop)
		self.addCleanup(frappe.set_user, "Administrator")
		if not frappe.db.exists("GitLab Project", OWN):
			frappe.get_doc({"doctype": "GitLab Project", "title": OWN, "project_id": OWN}).insert(ignore_permissions=True)
		groups = patch("phamos.cockpits.team_gitlab._project_groups", return_value=({OWN: "own"}, {OWN}))
		groups.start()
		self.addCleanup(groups.stop)

	def ctx(self, team=TEAM_A, day=TODAY):
		return ts.Context(team, day)

	def item(self, created, closed=None, parent=None):
		doc = frappe.get_doc(
			{
				"doctype": "GitLab Issue",
				"title": "Test item",
				"issue_id": frappe.generate_hash(length=8),
				"state": "closed" if closed else "opened",
				"created_at": created,
				"closed_at": closed,
				"gitlab_project": OWN,
				"parent_issue": parent,
			}
		)
		doc.flags.ignore_links = True
		return doc.insert(ignore_permissions=True).name


class TestWriting(SuccessTestCase):
	def test_each_success_once_and_posted(self):
		success = ts._success("x:1", "Delivery", "Shipped")
		self.assertTrue(ts.record_success(TEAM_A, success, day=TODAY))
		self.assertIsNone(ts.record_success(TEAM_A, success, day=TODAY))
		# the same key for another team is its own success
		self.assertTrue(ts.record_success(TEAM_B, success, day=TODAY))
		self.assertEqual(self.posted.call_count, 2)

	def test_a_failing_rule_does_not_stop_the_others(self):
		def broken(ctx):
			raise ValueError("boom")

		def fine(ctx):
			return [ts._success("fine:1", "Delivery", "Fine")]

		with patch.object(ts, "RULES", [broken, fine]):
			created = ts.run_rules(TEAM_A, TODAY)
		self.assertEqual(len(created), 1)


class TestDelivery(SuccessTestCase):
	def test_a_parent_with_all_children_closed(self):
		parent = self.item("2026-03-01 09:00:00", "2026-03-16 09:00:00")
		self.item("2026-03-02 09:00:00", "2026-03-05 09:00:00", parent=parent)
		self.item("2026-03-02 09:00:00", "2026-03-06 09:00:00", parent=parent)
		self.assertEqual([s.key for s in ts.parent_item_shipped(self.ctx())], [f"parent:{parent}"])
		# one child still open: not yet
		self.item("2026-03-02 09:00:00", parent=parent)
		self.assertEqual(ts.parent_item_shipped(self.ctx()), [])

	def test_milestone_closed_on_time(self):
		milestone = frappe.get_doc(
			{"doctype": "GitLab Milestones", "title": "Go-live", "gitlab_project": OWN, "state": "closed", "due_date": "2026-03-20", "milestone_id": 99}
		)
		milestone.flags.ignore_links = True
		milestone.insert(ignore_permissions=True)
		frappe.db.set_value("GitLab Milestones", milestone.name, "modified", "2026-03-17 10:00:00", update_modified=False)
		self.assertEqual([s.key for s in ts.milestone_on_time(self.ctx())], [f"milestone:{milestone.name}"])

	def test_record_months(self):
		def month(start, closed, median):
			return frappe._dict(start=start, closed_total=closed, work_item_median=median)

		fake = frappe._dict(
			months=[month(date(2025, m, 1), 10, 3.0) for m in range(4, 13)]
			+ [month(date(2026, 1, 1), 12, 2.5), month(date(2026, 2, 1), 20, 1.5), month(date(2026, 3, 1), 1, 9)]
		)
		ctx = self.ctx()
		ctx._gitlab = fake
		keys = sorted(s.key for s in ts.record_month(ctx))
		self.assertEqual(keys, ["record_closed:2026-02", "record_speed:2026-02"])


class TestImplementations(SuccessTestCase):
	def setUp(self):
		super().setUp()
		name = frappe.get_all("Implementation", limit=1, pluck="name")
		if not name:
			self.skipTest("needs an Implementation")
		self.implementation = name[0]
		frappe.db.set_value("Implementation", self.implementation, "team", TEAM_A, update_modified=False)

	def version(self, field, old, new, created="2026-03-17 10:00:00"):
		doc = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Implementation",
				"docname": self.implementation,
				"data": frappe.as_json({"changed": [[field, old, new]]}),
			}
		)
		doc.db_insert()
		frappe.db.set_value("Version", doc.name, "creation", created, update_modified=False)
		return doc.name

	def test_maturity_up_and_forecast_better(self):
		up = self.version("maturity_level", "2 - Initial", "3 - Development")
		self.version("maturity_level", "4 - Go Live", "3 - Development")  # down: nothing
		better = self.version("forecast", "3 ☁️ - x", "1 ☀️ - y")
		old = self.version("maturity_level", "1 - x", "2 - y", created="2026-02-01 10:00:00")  # too old
		keys = {s.key for s in ts.implementation_steps(self.ctx())}
		self.assertEqual(keys, {f"maturity:{up}", f"forecast:{better}"})
		self.assertNotIn(f"maturity:{old}", keys)

	def test_a_module_at_its_target(self):
		row = frappe.get_doc(
			{
				"doctype": "Implementation Item",
				"parent": self.implementation,
				"parenttype": "Implementation",
				"parentfield": "modules",
				"module": "DATEV",
				"current_level": 3,
				"target_level": 3,
			}
		)
		row.db_insert()
		frappe.db.set_value("Implementation Item", row.name, "modified", "2026-03-17 10:00:00", update_modified=False)
		self.assertIn(f"module:{row.name}:3", {s.key for s in ts.module_at_target(self.ctx())})


class TestTimesheetsAndIdeas(SuccessTestCase):
	def test_everyone_booked_and_a_streak(self):
		good = frappe._dict(known=True, available_known=40, booked_rate=97)
		with patch.object(ts, "_booked_rows", return_value=[good, good]), patch(
			"phamos.cockpits.team_hours.totals", return_value=frappe._dict(booked_rate=96)
		):
			keys = {s.key.split(":")[0] for s in ts.complete_timesheets(self.ctx())}
		self.assertEqual(keys, {"timesheets_month", "timesheets_streak"})
		low = frappe._dict(known=True, available_known=40, booked_rate=80)
		with patch.object(ts, "_booked_rows", return_value=[good, low]), patch(
			"phamos.cockpits.team_hours.totals", return_value=frappe._dict(booked_rate=90)
		):
			self.assertEqual(ts.complete_timesheets(self.ctx()), [])

	def test_a_team_idea_harvested(self):
		idea = frappe.get_doc(
			{"doctype": "Idea", "user": self.users[self.ben], "title": "Standup", "stage": "Harvest", "team": TEAM_A, "harvested_on": "2026-03-17 10:00:00"}
		)
		idea.db_insert()
		self.assertEqual([s.key for s in ts.idea_harvested(self.ctx())], [f"idea:{idea.name}"])
		self.assertEqual(ts.idea_harvested(self.ctx(TEAM_B)), [])


class TestPickedUp(SuccessTestCase):
	def test_an_idle_issue_without_a_team(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Old printer bug"}).insert(ignore_permissions=True)
		frappe.db.set_value("Issue", issue.name, "creation", "2026-01-10 09:00:00", update_modified=False)
		for name, data, created in (
			("v-old", {"changed": [["status", "Open", "Replied"]]}, "2026-02-01 10:00:00"),
			("v-team", {"changed": [["custom_team", None, TEAM_A]]}, "2026-03-17 10:00:00"),
		):
			doc = frappe.get_doc({"doctype": "Version", "ref_doctype": "Issue", "docname": issue.name, "data": frappe.as_json(data)})
			doc.db_insert()
			frappe.db.set_value("Version", doc.name, {"creation": created, "owner": self.users[self.ben]}, update_modified=False)
		found = ts.picked_up(self.ctx())
		self.assertEqual([s.key for s in found], [f"picked_up:{issue.name}"])
		self.assertEqual(found[0].employee, self.ben)

	def test_recently_active_is_not_picked_up(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Fresh"}).insert(ignore_permissions=True)
		doc = frappe.get_doc(
			{"doctype": "Version", "ref_doctype": "Issue", "docname": issue.name, "data": frappe.as_json({"changed": [["custom_team", None, TEAM_A]]})}
		)
		doc.db_insert()
		frappe.db.set_value("Version", doc.name, "creation", "2026-03-17 10:00:00", update_modified=False)
		frappe.db.set_value("Issue", issue.name, "creation", "2026-03-10 09:00:00", update_modified=False)
		self.assertEqual(ts.picked_up(self.ctx()), [])


class TestSla(SuccessTestCase):
	def test_only_while_sla_is_on(self):
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 0)
		self.assertEqual(ts.sla_successes(self.ctx()), [])
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Fast", "custom_team": TEAM_A}).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Issue", issue.name, {"first_responded_on": "2026-03-17 10:00:00", "response_by": "2026-03-17 12:00:00"}, update_modified=False
		)
		self.assertIn(f"sla_response:{issue.name}", {s.key for s in ts.sla_successes(self.ctx())})


class TestManual(SuccessTestCase):
	def test_kudos_show_the_giver_and_stay_in_the_team(self):
		frappe.set_user(self.users[self.anna])
		name = ts.give_kudos(TEAM_A, self.ben, "Thanks for the DATEV fix")
		doc = frappe.get_doc("Team Success", name)
		self.assertEqual((doc.success_type, doc.employee, doc.given_by), ("Kudos", self.ben, self.users[self.anna]))
		with self.assertRaises(frappe.ValidationError):
			ts.give_kudos(TEAM_A, self.cara, "Not in the team")
		with self.assertRaises(frappe.ValidationError):
			ts.give_kudos(TEAM_A, self.anna, "Myself")

	def test_customer_praise(self):
		customer = frappe.get_all("Customer", limit=1, pluck="name")
		if not customer:
			self.skipTest("needs a Customer")
		frappe.set_user(self.users[self.ben])
		name = ts.add_customer_praise(TEAM_A, customer[0], "Great go-live", self.anna)
		doc = frappe.get_doc("Team Success", name)
		self.assertEqual((doc.success_type, doc.customer, doc.given_by, doc.employee), ("Customer praise", customer[0], self.users[self.ben], self.anna))
