# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Check-in and check-out from the Personal Cockpit (#1571), with Employee-only users."""

import unittest
from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, get_datetime, now_datetime, today

from phamos.api import personal_checkin as checkin
from phamos.api import personal_cockpit as pc
from phamos.cockpits.defaults import CHECKIN_DEVICE_ID

USER = "ci-a@example.com"
OTHER = "ci-b@example.com"
NO_EMPLOYEE = "ci-c@example.com"


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")


def _ensure_employee(user):
	name = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if name:
		return name
	company = frappe.db.get_value("Company", {}, "name")
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": user.split("@")[0],
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"status": "Active",
				"company": company,
				"user_id": user,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


@unittest.skipUnless(frappe.db.exists("DocType", "Employee Checkin"), "HRMS is not installed")
class TestPersonalCheckin(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (USER, OTHER, NO_EMPLOYEE):
			_ensure_user(user)
		self.employee = _ensure_employee(USER)
		self.other_employee = _ensure_employee(OTHER)
		geo = patch.object(checkin, "_geolocation_required", return_value=False)
		geo.start()
		self.addCleanup(geo.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _log(self, log_type, time, employee=None):
		"""A log with an explicit time, made as Administrator (who may set the permlevel-1 time)."""
		frappe.set_user("Administrator")
		return frappe.get_doc(
			{"doctype": "Employee Checkin", "employee": employee or self.employee, "log_type": log_type, "time": time}
		).insert(ignore_permissions=True)

	def test_no_employee_means_nothing_to_show(self):
		frappe.set_user(NO_EMPLOYEE)
		state = pc.get_checkin_state()
		self.assertTrue(state["available"])
		self.assertIsNone(state["employee"])
		self.assertFalse(state["can_checkin"])
		with self.assertRaises(frappe.ValidationError):
			pc.add_checkin("IN")

	def test_check_in_uses_server_time_and_alternates(self):
		frappe.set_user(USER)
		state = pc.get_checkin_state()
		self.assertEqual((state["next_action"], state["can_checkin"]), ("IN", True))

		result = pc.add_checkin("IN")
		log = frappe.get_doc("Employee Checkin", result["log"]["name"])
		self.assertEqual((log.employee, log.log_type, log.device_id), (self.employee, "IN", CHECKIN_DEVICE_ID))
		self.assertLess(abs((get_datetime(log.time) - now_datetime()).total_seconds()), 5)
		self.assertEqual(result["state"]["next_action"], "OUT")
		self.assertEqual([row["name"] for row in result["state"]["today"]["logs"]], [log.name])

		with self.assertRaises(frappe.ValidationError):
			pc.add_checkin("IN")  # double click or a second tab
		self.assertEqual(pc.add_checkin("OUT")["state"]["next_action"], "IN")
		with self.assertRaises(frappe.ValidationError):
			pc.add_checkin("OUT")

	def test_unknown_log_type_is_refused(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.add_checkin("BREAK")

	def test_stale_check_in_from_an_earlier_day(self):
		self._log("IN", f"{add_days(today(), -1)} 08:00:00")
		frappe.set_user(USER)
		state = pc.get_checkin_state()
		self.assertTrue(state["stale_in"])
		self.assertEqual(state["next_action"], "OUT")
		self.assertEqual(state["today"]["logs"], [])

	def test_worked_minutes_today(self):
		day = today()
		for log_type, time in (("IN", "08:00"), ("OUT", "12:00"), ("IN", "13:00")):
			self._log(log_type, f"{day} {time}:00")
		frappe.set_user(USER)
		with patch.object(checkin, "now_datetime", return_value=get_datetime(f"{day} 15:00:00")):
			state = pc.get_checkin_state()
		self.assertEqual(state["today"]["worked_minutes"], 4 * 60 + 2 * 60)
		self.assertEqual(state["today"]["open_since"], get_datetime(f"{day} 13:00:00"))

	def test_worked_minutes_ignores_an_out_without_in(self):
		now = get_datetime("2026-10-16 18:00:00")
		logs = [
			{"log_type": "OUT", "time": "2026-10-16 07:00:00"},
			{"log_type": "IN", "time": "2026-10-16 08:00:00"},
			{"log_type": "IN", "time": "2026-10-16 08:30:00"},
			{"log_type": "OUT", "time": "2026-10-16 10:00:00"},
		]
		self.assertEqual(checkin.worked_minutes(logs, now), 120)
		self.assertEqual(checkin.next_action(None), "IN")
		self.assertEqual(checkin.next_action({"log_type": "IN"}), "OUT")

	def test_revoke_a_fresh_check_in(self):
		frappe.set_user(USER)
		name = pc.add_checkin("IN")["log"]["name"]
		state = pc.revoke_checkin(name)
		self.assertFalse(frappe.db.exists("Employee Checkin", name))
		self.assertEqual(state["next_action"], "IN")

	def test_revoke_is_limited_in_time(self):
		frappe.set_user(USER)
		name = pc.add_checkin("IN")["log"]["name"]
		later = now_datetime() + timedelta(minutes=2)
		with patch.object(checkin, "now_datetime", return_value=later):
			with self.assertRaises(frappe.ValidationError):
				pc.revoke_checkin(name)
		self.assertTrue(frappe.db.exists("Employee Checkin", name))

	def test_someone_elses_check_in_cannot_be_revoked(self):
		theirs = self._log("IN", now_datetime(), employee=self.other_employee)
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			pc.revoke_checkin(theirs.name)

	def test_location_is_required_when_hr_tracks_it(self):
		frappe.set_user(USER)
		with patch.object(checkin, "_geolocation_required", return_value=True):
			with self.assertRaises(frappe.ValidationError):
				pc.add_checkin("IN")

	def test_changes_are_published_to_the_employees_user(self):
		with patch("frappe.publish_realtime") as publish:
			log = self._log("IN", now_datetime())
		users = {call.kwargs.get("user") for call in publish.call_args_list if call.args[0] == "cockpit_checkin_changed"}
		self.assertEqual(users, {USER})
		self.assertTrue(log.name)

	def test_without_hrms_nothing_is_offered(self):
		frappe.set_user(USER)
		with patch.object(checkin, "available", return_value=False):
			state = pc.get_checkin_state()
			self.assertEqual((state["available"], state["employee"], state["can_checkin"]), (False, None, False))
			with self.assertRaises(frappe.ValidationError):
				pc.add_checkin("IN")
