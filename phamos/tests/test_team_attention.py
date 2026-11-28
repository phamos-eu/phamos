# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Needs attention (#2235): idle records by changes, comments and timesheets; only the team's;
SLA only while it runs; one morning summary with new items only, each item announced once."""

from datetime import datetime
from unittest.mock import patch

import frappe

from phamos.cockpits import team_attention as ta
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase

NOW = datetime(2026, 3, 18, 7, 30)  # a Wednesday


class AttentionTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 0)
		posted = patch("phamos.cockpits.team_successes._post_in_team_chat")
		self.posted = posted.start()
		self.addCleanup(posted.stop)

	def issue(self, team=TEAM_A, modified="2026-03-01 09:00:00", **values):
		values.setdefault("status", "Open")
		doc = frappe.get_doc({"doctype": "Issue", "subject": "Printer", "custom_team": team}).insert(ignore_permissions=True)
		frappe.db.set_value("Issue", doc.name, {"modified": modified, "creation": "2026-02-01 09:00:00", **values}, update_modified=False)
		return doc.name

	def task(self, team=TEAM_A, modified="2026-03-01 09:00:00"):
		doc = frappe.get_doc({"doctype": "Task", "subject": "Export", "custom_team": team}).insert(ignore_permissions=True)
		frappe.db.set_value("Task", doc.name, {"modified": modified, "creation": "2026-02-01 09:00:00"}, update_modified=False)
		return doc.name

	def names(self, items):
		return {i.name for i in items}


class TestIdle(AttentionTestCase):
	def test_idle_by_changes_comments_and_mails(self):
		idle = self.issue()
		changed = self.issue(modified="2026-03-17 09:00:00")
		commented = self.issue()
		comment = frappe.get_doc(
			{"doctype": "Comment", "comment_type": "Comment", "reference_doctype": "Issue", "reference_name": commented, "content": "x"}
		)
		comment.db_insert()
		frappe.db.set_value("Comment", comment.name, "creation", "2026-03-16 09:00:00", update_modified=False)
		mailed = self.issue()
		mail = frappe.get_doc(
			{"doctype": "Communication", "subject": "Re", "communication_type": "Communication", "reference_doctype": "Issue", "reference_name": mailed}
		)
		mail.db_insert()
		frappe.db.set_value("Communication", mail.name, "creation", "2026-03-15 09:00:00", update_modified=False)
		closed = self.issue(status="Closed")
		found = self.names(ta.idle_items(TEAM_A, NOW))
		self.assertIn(idle, found)
		self.assertFalse({changed, commented, mailed, closed} & found)

	def test_a_timesheet_keeps_a_task_active(self):
		idle = self.task()
		booked = self.task()
		ts = frappe.get_doc({"doctype": "Timesheet", "employee": self.anna, "time_logs": []})
		ts.append("time_logs", {"activity_type": frappe.get_all("Activity Type", limit=1, pluck="name")[0], "from_time": "2026-03-16 09:00:00", "hours": 1, "task": booked})
		ts.flags.ignore_validate = True
		ts.flags.ignore_links = True
		ts.insert(ignore_permissions=True)
		cancelled_on = self.task()
		cancelled = frappe.copy_doc(ts)
		cancelled.time_logs[0].task = cancelled_on
		cancelled.flags.ignore_validate = True
		cancelled.flags.ignore_links = True
		cancelled.insert(ignore_permissions=True)
		frappe.db.set_value("Timesheet", cancelled.name, "docstatus", 2, update_modified=False)
		found = self.names(ta.idle_items(TEAM_A, NOW))
		self.assertIn(idle, found)
		self.assertNotIn(booked, found)
		self.assertIn(cancelled_on, found)

	def test_only_the_teams_records(self):
		other = self.issue(team=TEAM_B)
		self.assertNotIn(other, self.names(ta.idle_items(TEAM_A, NOW)))

	def test_through_a_project_of_the_team(self):
		name = self.issue(team=None, project="_Test Attention Project")
		with patch("phamos.cockpits.teams.team_projects", return_value=["_Test Attention Project"]):
			self.assertIn(name, self.names(ta.idle_items(TEAM_A, NOW)))

	def test_waiting_on_the_customer_is_not_idle(self):
		replied = self.issue(status="Replied")
		held = self.issue(status="On Hold")
		found = self.names(ta.idle_items(TEAM_A, NOW))
		self.assertFalse({replied, held} & found)

	def test_the_days_are_a_setting(self):
		name = self.issue(modified="2026-03-13 09:00:00")  # five days
		self.assertNotIn(name, self.names(ta.idle_items(TEAM_A, NOW)))
		frappe.db.set_single_value("Cockpit Settings", "team_attention_idle_days", 4)
		self.assertIn(name, self.names(ta.idle_items(TEAM_A, NOW)))


class TestSla(AttentionTestCase):
	def sla_issue(self, **values):
		return self.issue(modified="2026-03-18 07:00:00", service_level_agreement="_Test SLA", agreement_status="First Response Due", **values)

	def test_only_while_sla_is_on_and_running(self):
		missed = self.sla_issue(response_by="2026-03-17 12:00:00")
		self.assertEqual(ta.sla_items(TEAM_A, NOW), [])
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		due = self.sla_issue(response_by="2026-03-17 12:00:00", first_responded_on="2026-03-17 11:00:00", sla_resolution_by="2026-03-18 20:00:00")
		later = self.sla_issue(sla_resolution_by="2026-03-25 20:00:00")
		switched_off = self.issue(modified="2026-03-18 07:00:00", response_by="2026-03-17 12:00:00")  # no SLA any more
		fulfilled = self.sla_issue(response_by="2026-03-17 12:00:00")
		frappe.db.set_value("Issue", fulfilled, "agreement_status", "Fulfilled", update_modified=False)
		kinds = {i.name: i.kind for i in ta.sla_items(TEAM_A, NOW)}
		self.assertEqual(kinds.get(missed), "response_missed")
		self.assertEqual(kinds.get(due), "resolution_due")  # answered: the resolution counts
		self.assertFalse({later, switched_off, fulfilled} & set(kinds))
		# an SLA item is listed once, not again as idle
		self.assertEqual([i.name for i in ta.attention_items(TEAM_A, NOW)].count(missed), 1)


class TestSummary(AttentionTestCase):
	def first_run(self):
		"""The team's first run records what lies around already, silently."""
		self.issue(modified="2026-02-01 09:00:00")
		self.assertEqual(ta.post_summary(TEAM_A, NOW), 0)
		self.posted.assert_not_called()

	def test_each_item_once(self):
		self.first_run()
		new = self.issue(modified="2026-03-07 12:00:00")
		self.assertEqual(ta.post_summary(TEAM_A, NOW), 1)
		html = self.posted.call_args[0][1]
		self.assertIn(f"/team-cockpit/issues/list/{new}", html)
		# a late, repeated or skipped run does not post it again
		self.posted.reset_mock()
		self.assertEqual(ta.post_summary(TEAM_A, NOW), 0)
		self.assertEqual(ta.post_summary(TEAM_A, datetime(2026, 3, 23, 7, 45)), 0)
		self.posted.assert_not_called()
		# it moved and lies around again: news again
		frappe.db.set_value("Issue", new, "modified", "2026-03-10 09:00:00", update_modified=False)
		self.assertEqual(ta.post_summary(TEAM_A, datetime(2026, 3, 23, 7, 30)), 1)

	def test_due_then_missed_is_one_notice(self):
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		self.first_run()
		self.issue(modified="2026-03-18 07:00:00", service_level_agreement="_Test SLA", agreement_status="First Response Due", response_by="2026-03-18 12:00:00")
		self.assertEqual(ta.post_summary(TEAM_A, NOW), 1)
		self.assertEqual(ta.post_summary(TEAM_A, datetime(2026, 3, 19, 7, 30)), 0)

	def test_a_short_sla_is_still_announced(self):
		# created and due between two summaries: announced (as missed) at the next one
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		self.first_run()
		self.issue(modified="2026-03-18 08:00:00", service_level_agreement="_Test SLA", agreement_status="First Response Due", response_by="2026-03-18 12:00:00")
		self.assertEqual(ta.post_summary(TEAM_A, datetime(2026, 3, 19, 7, 30)), 1)

	def test_at_most_fifteen_listed(self):
		self.first_run()
		for _i in range(17):
			self.issue(modified="2026-03-07 12:00:00")
		ta.post_summary(TEAM_A, NOW)
		html = self.posted.call_args[0][1]
		self.assertEqual(html.count("<li>"), 16)
		self.assertIn("2", html.split("<li>")[-1])

	def test_can_be_switched_off(self):
		frappe.db.set_single_value("Cockpit Settings", "team_attention_summary", 0)
		with patch.object(ta, "post_summary") as post:
			ta.post_all_summaries()
		post.assert_not_called()

	def test_subjects_are_escaped(self):
		self.first_run()
		name = self.issue(modified="2026-03-07 12:00:00")
		frappe.db.set_value("Issue", name, "subject", "<img src=x onerror=alert(1)>", update_modified=False)
		ta.post_summary(TEAM_A, NOW)
		self.assertNotIn("<img", self.posted.call_args[0][1])


class TestPage(AttentionTestCase):
	def test_the_page_lists_the_active_teams_records_as_the_user(self):
		from phamos.api import team_cockpit

		mine = self.issue()
		other = self.issue(team=TEAM_B)
		with patch("phamos.cockpits.teams.require_active_team", return_value=TEAM_A), patch.object(
			team_cockpit, "check_app_permission", return_value=True
		):
			data = team_cockpit.get_team_attention()
			self.assertIn(mine, {i["name"] for i in data["items"]})
			self.assertNotIn(other, {i["name"] for i in data["items"]})
			self.assertIsInstance(data["items"][0]["assignees"], list)
			with patch.object(ta.frappe, "has_permission", side_effect=lambda doctype, *a, **k: doctype != "Task"):
				self.task()
				names = {i["doctype"] for i in team_cockpit.get_team_attention()["items"]}
		self.assertEqual(names, {"Issue"})
