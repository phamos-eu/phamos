# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team mates (#1978): status per person, live updates to the team, the team chat's members."""

from datetime import datetime
from unittest.mock import patch

import frappe

from phamos.api import team_cockpit
from phamos.cockpits import team_chat, team_status, teams
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase

NOW = datetime(2026, 3, 4, 11, 0)  # a Wednesday


class TeamMatesTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01")
		self.assign(self.cara, TEAM_B, "2026-01-01")
		self.anna_user = frappe.db.get_value("Employee", self.anna, "user_id")
		self.ben_user = frappe.db.get_value("Employee", self.ben, "user_id")
		self.cara_user = frappe.db.get_value("Employee", self.cara, "user_id")
		for employee in (self.anna, self.ben, self.cara):
			frappe.db.set_value("Employee", employee, "holiday_list", None)

	def checkin(self, employee, log_type, time):
		doc = frappe.get_doc({"doctype": "Employee Checkin", "employee": employee, "log_type": log_type, "time": time})
		doc.flags.ignore_validate = True
		doc.db_insert()


class TestPresence(TeamMatesTestCase):
	def test_checked_in_since_and_not_checked_in(self):
		self.checkin(self.anna, "IN", "2026-03-04 08:12:00")
		self.assertEqual(team_status._presence(self.anna, NOW), {"presence": "checked_in", "since": "08:12"})
		# checked out again
		self.checkin(self.anna, "OUT", "2026-03-04 10:30:00")
		self.assertEqual(team_status._presence(self.anna, NOW), {"presence": "not_checked_in"})
		# an IN left over from yesterday does not count
		self.checkin(self.ben, "IN", "2026-03-03 08:00:00")
		self.assertEqual(team_status._presence(self.ben, NOW), {"presence": "not_checked_in"})

	def test_approved_leave_wins_and_shows_no_leave_type(self):
		self.checkin(self.anna, "IN", "2026-03-04 08:12:00")
		leave = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.anna,
				"leave_type": frappe.get_all("Leave Type", limit=1, pluck="name")[0],
				"from_date": "2026-03-02",
				"to_date": "2026-03-06",
				"status": "Approved",
				"docstatus": 1,
				"company": frappe.db.get_value("Employee", self.anna, "company"),
			}
		)
		leave.db_insert()
		self.assertEqual(team_status._presence(self.anna, NOW), {"presence": "absent"})

	def test_holiday_and_day_off(self):
		name = "_Test Team Mates Holidays"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True)
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{"holiday_date": "2026-03-04", "description": "Test holiday", "weekly_off": 0},
					{"holiday_date": "2026-03-07", "description": "Saturday", "weekly_off": 1},
				],
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", self.anna, "holiday_list", name)
		self.assertEqual(team_status._presence(self.anna, NOW), {"presence": "holiday"})
		self.assertEqual(team_status._presence(self.anna, datetime(2026, 3, 7, 11, 0)), {"presence": "day_off"})


class TestTimerAndFocus(TeamMatesTestCase):
	def timer(self, employee, rows, created=NOW):
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": employee,
				"project": frappe.get_all("Project", limit=1, pluck="name")[0],
				"from_time": created,
				"item": [{"from_time": f, "to_time": t} for f, t in rows],
			}
		)
		record.flags.ignore_validate = True
		record.flags.ignore_links = True
		record.insert(ignore_permissions=True, ignore_mandatory=True)
		frappe.db.set_value("Timesheet Record", record.name, "creation", created, update_modified=False)
		return record

	def test_running_paused_and_stopped(self):
		self.timer(self.anna, [("2026-03-04 09:00:00", None)])
		timer = team_status._timer(self.anna, NOW)
		self.assertEqual(timer["state"], "running")
		self.assertTrue(timer["project"])
		self.assertNotIn("elapsed_seconds", timer)
		# a break: the work row is closed, an open break row follows
		self.timer(self.ben, [("2026-03-04 09:00:00", "2026-03-04 10:00:00"), ("2026-03-04 10:00:00", None)])
		self.assertEqual(team_status._timer(self.ben, NOW)["state"], "paused")

	def test_an_old_draft_is_no_timer(self):
		self.timer(self.anna, [("2026-02-01 09:00:00", None)], created=datetime(2026, 2, 1, 9, 0))
		self.assertIsNone(team_status._timer(self.anna, NOW))

	def test_focus_until_its_limit(self):
		doc = frappe.get_doc(
			{
				"doctype": "Focus Session",
				"user": self.anna_user,
				"status": "Active",
				"started_at": "2026-03-04 10:30:00",
				"planned_minutes": 25,
				"planned_end": "2026-03-04 10:55:00",
			}
		)
		doc.db_insert()
		self.assertTrue(team_status._in_focus(self.anna_user, NOW))
		self.assertFalse(team_status._in_focus(self.anna_user, datetime(2026, 3, 4, 13, 0)))


class TestLiveUpdates(TeamMatesTestCase):
	def test_the_new_row_goes_to_the_team_only(self):
		sent = []
		with patch.object(team_status.frappe, "publish_realtime", side_effect=lambda event, message, user=None, **kw: sent.append((event, message, user))), patch.object(
			teams, "member_teams", return_value=[TEAM_A]
		):
			team_status.publish_member_status(self.ben)
		recipients = {user for _e, _m, user in sent}
		self.assertEqual(recipients, {self.anna_user, self.ben_user})
		self.assertTrue(all(event == team_status.EVENT and message["row"]["employee"] == self.ben for event, message, _u in sent))

	def test_the_page_lists_the_team_today(self):
		rows = team_status.team_mates(TEAM_A, NOW)
		self.assertEqual({r["employee"] for r in rows}, {self.anna, self.ben})


class TestTeamChat(TeamMatesTestCase):
	def test_members_follow_the_team_and_leavers_are_removed(self):
		channel = frappe._dict(name="chan", workspace="ws")
		admin = "Administrator"
		with patch.object(team_chat.issue_chat, "is_raven_installed", return_value=True), patch.object(
			team_chat.issue_chat, "is_enabled", return_value=True
		), patch.object(team_chat.issue_chat, "find_channel", return_value=channel), patch.object(
			team_chat.issue_chat, "_ensure_members"
		) as ensure, patch.object(
			team_chat.issue_chat, "channel_member_users", return_value=[self.anna_user, self.cara_user, admin]
		), patch.object(team_chat.issue_chat, "_remove_members") as remove:
			team_chat.sync_team_channel(TEAM_A)
		self.assertEqual(set(ensure.call_args.args[1]), {self.anna_user, self.ben_user})
		# cara is in another team: removed; Administrator sees every team: stays
		self.assertEqual(remove.call_args.args[1], [self.cara_user])

	def test_no_chat_yet_means_nothing_to_do(self):
		with patch.object(team_chat.issue_chat, "is_raven_installed", return_value=True), patch.object(
			team_chat.issue_chat, "is_enabled", return_value=True
		), patch.object(team_chat.issue_chat, "find_channel", return_value=None), patch.object(
			team_chat.issue_chat, "_ensure_members"
		) as ensure:
			team_chat.sync_team_channel(TEAM_A)
		ensure.assert_not_called()

	def test_someone_outside_the_team_cannot_open_its_chat(self):
		frappe.set_user(self.cara_user)
		self.addCleanup(frappe.set_user, "Administrator")
		with self.assertRaises(frappe.PermissionError):
			team_cockpit._team_doc(TEAM_A)
		self.assertEqual(team_cockpit._team_doc(TEAM_B).name, TEAM_B)
