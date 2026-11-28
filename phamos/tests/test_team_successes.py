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

	def milestone(self, state, due="2026-03-20"):
		doc = frappe.get_doc(
			{"doctype": "GitLab Milestones", "title": "Go-live", "gitlab_project": OWN, "state": state, "due_date": due, "milestone_id": frappe.generate_hash(length=6)}
		)
		doc.flags.ignore_links = True
		return doc.insert(ignore_permissions=True)

	def test_milestone_closed_on_time(self):
		milestone = self.milestone("active")
		milestone.state = "closed"
		milestone.save(ignore_permissions=True)
		self.assertTrue(milestone.closed_on)
		frappe.db.set_value("GitLab Milestones", milestone.name, "closed_on", "2026-03-17 10:00:00", update_modified=False)
		self.assertEqual([s.key for s in ts.milestone_on_time(self.ctx())], [f"milestone:{milestone.name}"])

	def test_a_resynced_milestone_is_not_closed_again(self):
		# first synced as closed (when it closed is unknown), then saved by every sync: never counts
		milestone = self.milestone("closed")
		milestone.description = "synced again"
		milestone.save(ignore_permissions=True)
		self.assertFalse(milestone.closed_on)
		self.assertEqual(ts.milestone_on_time(self.ctx()), [])

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

	def test_no_record_for_a_new_team(self):
		def month(start, closed, median):
			return frappe._dict(start=start, closed_total=closed, work_item_median=median)

		# eleven empty months and one item: not a record
		ctx = self.ctx()
		ctx._gitlab = frappe._dict(
			months=[month(date(2025, m, 1), 0, None) for m in range(4, 13)]
			+ [month(date(2026, 1, 1), 0, None), month(date(2026, 2, 1), 1, 2.0), month(date(2026, 3, 1), 0, None)]
		)
		self.assertEqual(ts.record_month(ctx), [])


class TestImplementations(SuccessTestCase):
	def setUp(self):
		super().setUp()
		name = frappe.get_all("Implementation", limit=1, pluck="name")
		if not name:
			self.skipTest("needs an Implementation")
		self.implementation = name[0]
		frappe.db.set_value("Implementation", self.implementation, "team", TEAM_A, update_modified=False)

	def version(self, field, old, new, created="2026-03-17 10:00:00", data=None):
		doc = frappe.get_doc(
			{
				"doctype": "Version",
				"ref_doctype": "Implementation",
				"docname": self.implementation,
				"data": frappe.as_json(data or {"changed": [[field, old, new]]}),
			}
		)
		doc.db_insert()
		frappe.db.set_value("Version", doc.name, "creation", created, update_modified=False)
		return doc.name

	def test_maturity_up_and_forecast_better(self):
		impl = self.implementation
		self.version("maturity_level", "2 - Initial", "3 - Development")
		self.version("maturity_level", "3 - Development", "2 - Initial")  # down: nothing
		self.version("maturity_level", "2 - Initial", "3 - Development")  # up again: the same success
		self.version("forecast", "3 ☁️ - x", "1 ☀️ - y")
		self.version("maturity_level", "1 - x", "2 - y", created="2026-02-01 10:00:00")  # too old
		found = ts.implementation_steps(self.ctx())
		self.assertEqual(sorted(s.key for s in found), sorted([f"maturity:{impl}:3", f"maturity:{impl}:3", f"forecast:{impl}:1:2026-03"]))
		for success in found:
			success.source = success.key.split(":")[0]
			ts.record_success(TEAM_A, success, day=TODAY)
		self.assertEqual(frappe.db.count("Team Success", {"team": TEAM_A, "source": "maturity"}), 1)

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
		# a save of the Implementation touches every row: without a level change, nothing
		frappe.db.set_value("Implementation Item", row.name, "modified", "2026-03-17 10:00:00", update_modified=False)
		self.assertNotIn(f"module:{row.name}:3", {s.key for s in ts.module_at_target(self.ctx())})
		self.version(None, None, None, data={"row_changed": [["modules", 0, row.name, [["current_level", 2, 3]]]]})
		self.assertIn(f"module:{row.name}:3", {s.key for s in ts.module_at_target(self.ctx())})

	def test_hours_budget_and_prediction(self):
		frappe.db.set_value(
			"Implementation", self.implementation, {"enable_time_limit": 1, "recurring_monthly": 1, "limit_hours": 20}, update_modified=False
		)
		frappe.get_doc(
			{"doctype": "Prediction", "parent": self.implementation, "parenttype": "Implementation", "parentfield": "prediction", "month_and_year": "2026-02", "prediction": 10}
		).db_insert()
		with patch.object(ts, "_implementation_hours", return_value=0):
			self.assertEqual(ts.implementation_hours(self.ctx()), [])  # dormant: no achievement
		with patch.object(ts, "_implementation_hours", return_value=10.5):
			keys = {s.key for s in ts.implementation_hours(self.ctx())}
		self.assertEqual(keys, {f"budget:{self.implementation}:2026-02", f"prediction:{self.implementation}:2026-02"})


class TestTimesheetsAndIdeas(SuccessTestCase):
	def test_everyone_booked_and_a_streak(self):
		good = frappe._dict(known=True, available_known=40, booked_rate=97)
		with patch.object(ts, "_booked_rows", return_value=[good, good]), patch(
			"phamos.cockpits.team_hours.totals", return_value=frappe._dict(booked_rate=96)
		):
			keys = {s.key.split(":")[0] for s in ts.complete_timesheets(self.ctx())}
		self.assertEqual(keys, {"timesheets_month", "timesheets_streak"})
		# a streak of four weeks, a week later five: still the one 4-week success of that streak
		streaks = []
		for day, weeks in ((TODAY, [96] * 4 + [50]), (date(2026, 3, 25), [96] * 5 + [50])):
			rates = iter(weeks)
			with patch.object(ts, "_booked_rows", return_value=[good]), patch(
				"phamos.cockpits.team_hours.totals", side_effect=lambda *a: frappe._dict(booked_rate=next(rates))
			):
				streaks.append([s.key for s in ts.complete_timesheets(self.ctx(day=day)) if s.key.startswith("timesheets_streak")])
		self.assertEqual(streaks[0], streaks[1])
		self.assertEqual(len(streaks[0]), 1)
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

	def test_a_recent_customer_mail_is_activity(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Discussed by mail"}).insert(ignore_permissions=True)
		frappe.db.set_value("Issue", issue.name, "creation", "2026-01-10 09:00:00", update_modified=False)
		doc = frappe.get_doc(
			{"doctype": "Version", "ref_doctype": "Issue", "docname": issue.name, "data": frappe.as_json({"changed": [["custom_team", None, TEAM_A]]})}
		)
		doc.db_insert()
		frappe.db.set_value("Version", doc.name, "creation", "2026-03-17 10:00:00", update_modified=False)
		mail = frappe.get_doc(
			{"doctype": "Communication", "subject": "Re", "communication_type": "Communication", "reference_doctype": "Issue", "reference_name": issue.name}
		)
		mail.db_insert()
		frappe.db.set_value("Communication", mail.name, "creation", "2026-03-12 09:00:00", update_modified=False)
		self.assertEqual(ts.picked_up(self.ctx()), [])

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
	def test_one_count_a_week_only_while_sla_is_on(self):
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 0)
		self.assertEqual(ts.sla_successes(self.ctx()), [])
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		for _i in range(2):
			issue = frappe.get_doc({"doctype": "Issue", "subject": "Fast", "custom_team": TEAM_A}).insert(ignore_permissions=True)
			frappe.db.set_value(
				"Issue", issue.name, {"first_responded_on": "2026-03-10 10:00:00", "response_by": "2026-03-10 12:00:00"}, update_modified=False
			)
		# resolved long ago, touched last week: does not count
		old = frappe.get_doc({"doctype": "Issue", "subject": "Old", "custom_team": TEAM_A}).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Issue", old.name, {"agreement_status": "Fulfilled", "sla_resolution_date": "2026-01-10 10:00:00", "modified": "2026-03-11 10:00:00"}, update_modified=False
		)
		found = ts.sla_successes(self.ctx())
		self.assertEqual([s.key for s in found], ["sla_response:2026-03-09"])
		self.assertIn("2", found[0].title)


class TestRunning(SuccessTestCase):
	def test_the_first_run_posts_nothing(self):
		def one(ctx):
			return [ts._success(f"one:{ctx.today}", "Delivery", "One")]

		with patch.object(ts, "RULES", [one]):
			ts.run_rules(TEAM_A, TODAY)
			self.posted.assert_not_called()
			ts.run_rules(TEAM_A, date(2026, 3, 19))
		self.posted.assert_called_once()

	def test_a_failing_insert_skips_only_that_success(self):
		def two(ctx):
			return [ts._success("bad:1", "Delivery", "Bad"), ts._success("good:1", "Delivery", "Good")]

		real = ts.record_success

		def flaky(team, success, **kwargs):
			if success.key == "bad:1":
				frappe.db.sql("insert into `tabTeam Success` (name) values ('x'), ('x')")  # duplicate: fails
			return real(team, success, **kwargs)

		with patch.object(ts, "RULES", [two]), patch.object(ts, "record_success", side_effect=flaky):
			created = ts.run_rules(TEAM_A, TODAY)
		self.assertEqual(len(created), 1)
		self.assertTrue(frappe.db.exists("Team Success", {"dedupe_key": f"{TEAM_A}|good:1"}))


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
