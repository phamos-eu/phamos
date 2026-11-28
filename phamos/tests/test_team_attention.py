# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Needs attention (#2235): idle records by changes, comments and timesheets; only the team's;
SLA only while it is on; one morning summary with new items only."""

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
		found = self.names(ta.idle_items(TEAM_A, NOW))
		self.assertIn(idle, found)
		self.assertNotIn(booked, found)

	def test_only_the_teams_records(self):
		other = self.issue(team=TEAM_B)
		self.assertNotIn(other, self.names(ta.idle_items(TEAM_A, NOW)))

	def test_the_days_are_a_setting(self):
		name = self.issue(modified="2026-03-13 09:00:00")  # five days
		self.assertNotIn(name, self.names(ta.idle_items(TEAM_A, NOW)))
		frappe.db.set_single_value("Cockpit Settings", "team_attention_idle_days", 4)
		self.addCleanup(frappe.db.set_single_value, "Cockpit Settings", "team_attention_idle_days", 10)
		self.assertIn(name, self.names(ta.idle_items(TEAM_A, NOW)))


class TestSla(AttentionTestCase):
	def test_only_while_sla_is_on(self):
		missed = self.issue(modified="2026-03-18 07:00:00", response_by="2026-03-17 12:00:00")
		self.assertEqual(ta.sla_items(TEAM_A, NOW), [])
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)
		due = self.issue(modified="2026-03-18 07:00:00", sla_resolution_by="2026-03-18 20:00:00")
		later = self.issue(modified="2026-03-18 07:00:00", sla_resolution_by="2026-03-25 20:00:00")
		answered = self.issue(modified="2026-03-18 07:00:00", response_by="2026-03-17 12:00:00", first_responded_on="2026-03-17 11:00:00")
		kinds = {i.name: i.kind for i in ta.sla_items(TEAM_A, NOW)}
		self.assertEqual(kinds.get(missed), "response_missed")
		self.assertEqual(kinds.get(due), "resolution_due")
		self.assertNotIn(later, kinds)
		self.assertNotIn(answered, kinds)
		# an SLA item is listed once, not again as idle
		self.assertEqual([i.name for i in ta.attention_items(TEAM_A, NOW)].count(missed), 1)


class TestSummary(AttentionTestCase):
	def test_once_with_new_items_only(self):
		new = self.issue(modified="2026-03-07 12:00:00")  # idle since 2026-03-17 12:00: new
		old = self.issue(modified="2026-03-01 09:00:00")  # idle for days already
		self.assertEqual(self.names(ta.new_items(TEAM_A, NOW)), {new})
		self.assertEqual(ta.post_summary(TEAM_A, NOW), 1)
		self.posted.assert_called_once()
		html = self.posted.call_args[0][1]
		self.assertIn(f"/team-cockpit/issues/list/{new}", html)
		self.assertNotIn(old, html)
		# the next morning the same item is not new any more
		self.posted.reset_mock()
		self.assertEqual(ta.post_summary(TEAM_A, datetime(2026, 3, 19, 7, 30)), 0)
		self.posted.assert_not_called()

	def test_monday_covers_the_weekend(self):
		weekend = self.issue(modified="2026-03-04 12:00:00")  # idle since Saturday 2026-03-14
		monday = datetime(2026, 3, 16, 7, 30)
		self.assertIn(weekend, self.names(ta.new_items(TEAM_A, monday)))

	def test_subjects_are_escaped(self):
		name = self.issue(modified="2026-03-07 12:00:00")
		frappe.db.set_value("Issue", name, "subject", "<img src=x onerror=alert(1)>", update_modified=False)
		ta.post_summary(TEAM_A, NOW)
		self.assertNotIn("<img", self.posted.call_args[0][1])
