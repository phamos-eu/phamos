# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team appointments with leave and public holidays (#1979). Mailcow calls are patched, as in the
General Management tests: the local site writes to the real SOGo."""

from unittest.mock import patch

import frappe

from phamos.api import team_cockpit
from phamos.cockpits import teams
from phamos.events import team_daily_schedule
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase

MAILBOX = "team-appointments@example.com"


class TeamAppointmentsTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		from phamos.setup.event_schedule import ensure_event_schedule_fields

		ensure_event_schedule_fields()
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01")
		self.assign(self.cara, TEAM_B, "2026-01-01")
		self.users = {e: frappe.db.get_value("Employee", e, "user_id") for e in (self.anna, self.ben, self.cara)}
		if not frappe.db.exists("Email Account", MAILBOX):
			account = frappe.new_doc("Email Account")
			account.update({"name": MAILBOX, "email_account_name": MAILBOX, "email_id": MAILBOX})
			account.db_insert()
		if not frappe.db.exists("Mailcow DAV Password", {"user": MAILBOX}):
			frappe.get_doc({"doctype": "Mailcow DAV Password", "user": MAILBOX, "dav_password": "x"}).insert()
		frappe.db.set_value("Team", TEAM_A, "team_mailbox", MAILBOX)
		team_daily_schedule._email_for_account.cache_clear()
		for target in ("_put_ics_upsert", "_delete_uid_for_mailbox"):
			p = patch.object(team_daily_schedule, target, return_value=(True, None))
			p.start()
			self.addCleanup(p.stop)
		self.enqueue = patch.object(frappe, "enqueue").start()
		self.addCleanup(patch.stopall)
		self.addCleanup(frappe.set_user, "Administrator")
		for p in (patch.object(team_cockpit, "check_app_permission", return_value=True),):
			p.start()

	def run_jobs(self):
		"""Run the queued invite jobs (Mailcow patched), as test_general_management_cockpit does."""
		job = "phamos.events.team_daily_schedule.run_sync_plan_in_background"
		for call in self.enqueue.call_args_list:
			if call.args[:1] != (job,):
				continue
			kwargs = call.kwargs
			with patch.object(frappe, "publish_realtime"), patch.object(frappe.db, "commit"):
				team_daily_schedule.run_sync_plan_in_background(kwargs["doctype"], kwargs["name"], kwargs["plan"], kwargs["user"])
		self.enqueue.reset_mock()

	def as_member_of(self, employee, team):
		frappe.set_user(self.users[employee])
		return patch.object(teams, "require_active_team", return_value=team)

	def appointment(self, **values):
		return {
			"subject": "Daily standup",
			"start": "2026-12-01 09:00:00",
			"end": "2026-12-01 09:15:00",
			"email_account": MAILBOX,
			"required_attendees": ["a@example.com"],
			"optional_attendees": [],
			**values,
		}


class TestPlanning(TeamAppointmentsTestCase):
	def test_a_member_plans_changes_and_cancels(self):
		with self.as_member_of(self.ben, TEAM_A):
			self.assertFalse(frappe.has_permission("Team", "write"))
			saved = team_cockpit.save_appointment(self.appointment())
			# the invite goes out in a job, as for General Management
			jobs = [c for c in self.enqueue.call_args_list if c.args[:1] == ("phamos.events.team_daily_schedule.run_sync_plan_in_background",)]
			self.assertEqual(len(jobs), 1)
			self.run_jobs()
			listed = team_cockpit.get_team_appointments()
			self.assertEqual([a["name"] for a in listed["appointments"]], [saved["name"]])
			team_cockpit.save_appointment(self.appointment(name=saved["name"], subject="Standup"))
			self.run_jobs()
			self.assertEqual(team_cockpit.get_team_appointments()["appointments"][0]["subject"], "Standup")
			team_cockpit.delete_appointment(saved["name"])
			self.assertEqual(team_cockpit.get_team_appointments()["appointments"], [])

	def test_the_whole_team_is_invited_by_default(self):
		for employee in (self.anna, self.ben):
			frappe.db.set_value("Employee", employee, "company_email", None)
		with self.as_member_of(self.ben, TEAM_A):
			defaults = team_cockpit.get_team_appointments()["default_attendees"]
		self.assertEqual(set(defaults), {self.users[self.anna], self.users[self.ben]})

	def test_another_team_cannot_reach_the_appointments(self):
		with self.as_member_of(self.ben, TEAM_A):
			saved = team_cockpit.save_appointment(self.appointment())
		self.run_jobs()
		frappe.set_user(self.users[self.cara])
		# cara's active team is her own; TEAM_A's rows are not hers to change
		with patch.object(teams, "require_active_team", return_value=TEAM_B):
			self.assertEqual(team_cockpit.get_team_appointments()["appointments"], [])
			with self.assertRaises(frappe.ValidationError):
				team_cockpit.delete_appointment(saved["name"])
		# and she cannot make TEAM_A her active team
		with self.assertRaises(frappe.PermissionError):
			teams.set_active_team(TEAM_A)


class TestTeamMailbox(TeamAppointmentsTestCase):
	"""Invites go out only from the team's shared mailbox (decision 4 of #1979)."""

	OTHER = "someone-else@example.com"

	def test_only_the_team_mailbox_is_offered_and_accepted(self):
		if not frappe.db.exists("Email Account", self.OTHER):
			account = frappe.new_doc("Email Account")
			account.update({"name": self.OTHER, "email_account_name": self.OTHER, "email_id": self.OTHER})
			account.db_insert()
		if not frappe.db.exists("Mailcow DAV Password", {"user": self.OTHER}):
			frappe.get_doc({"doctype": "Mailcow DAV Password", "user": self.OTHER, "dav_password": "x"}).insert()
		with self.as_member_of(self.ben, TEAM_A):
			self.assertEqual([m.name for m in team_cockpit.get_appointment_options()["mailboxes"]], [MAILBOX])
			with self.assertRaises(frappe.ValidationError):
				team_cockpit.save_appointment(self.appointment(email_account=self.OTHER))

	def test_without_a_team_mailbox_nothing_is_sent(self):
		frappe.db.set_value("Team", TEAM_A, "team_mailbox", None)
		with self.as_member_of(self.ben, TEAM_A):
			self.assertFalse(team_cockpit.get_team_appointments()["has_mailbox"])
			with self.assertRaises(frappe.ValidationError):
				team_cockpit.save_appointment(self.appointment())


class TestLeaveLayer(TeamAppointmentsTestCase):
	def test_absent_without_leave_type_and_holidays(self):
		leave_type = frappe.get_all("Leave Type", limit=1, pluck="name")[0]
		for employee, from_date, to_date in ((self.ben, "2026-12-02", "2026-12-04"), (self.cara, "2026-12-02", "2026-12-02")):
			frappe.get_doc(
				{
					"doctype": "Leave Application",
					"employee": employee,
					"leave_type": leave_type,
					"from_date": from_date,
					"to_date": to_date,
					"status": "Approved",
					"docstatus": 1,
					"company": frappe.db.get_value("Employee", employee, "company"),
				}
			).db_insert()
		name = "_Test Team Appointments Holidays"
		if frappe.db.exists("Holiday List", name):
			frappe.delete_doc("Holiday List", name, force=True)
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": name,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [
					{"holiday_date": "2026-12-25", "description": "Christmas", "weekly_off": 0},
					{"holiday_date": "2026-12-05", "description": "Saturday", "weekly_off": 1},
				],
			}
		).insert(ignore_permissions=True)
		for employee in (self.anna, self.ben, self.cara):
			frappe.db.set_value("Employee", employee, "holiday_list", name)
		with self.as_member_of(self.ben, TEAM_A):
			layer = team_cockpit.get_team_absences("2026-12-01", "2026-12-31")
		# only the team's people; no leave type in the answer
		self.assertEqual([a["employee"] for a in layer["absences"]], [self.ben])
		self.assertNotIn("leave_type", layer["absences"][0])
		# public holidays, not weekly offs
		self.assertEqual([(str(h["date"]), h["description"]) for h in layer["holidays"]], [("2026-12-25", "Christmas")])
		# once per holiday, with the team's people it applies to
		self.assertEqual(len(layer["holidays"][0]["people"]), 2)

	def test_a_long_period_is_refused(self):
		with self.as_member_of(self.ben, TEAM_A), self.assertRaises(frappe.ValidationError):
			team_cockpit.get_team_absences("2026-01-01", "2026-12-31")
