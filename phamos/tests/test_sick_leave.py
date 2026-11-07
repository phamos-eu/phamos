# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sick days from the Sick Leave Types setting (phamos/phamos#1834).

Leave without pay types keep HRMS from asking for allocations. SOGo is patched out, because
every Leave Application is mirrored as a calendar Event (milestone 68, Phase 2).
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import personal_leave
from phamos.mailcow_integration.caldav import client
from phamos.phamos.hr import sick_leave
from phamos.tests.test_mailcow_sync_event import _ensure_status_field, _ensure_user
from phamos.tests.test_personal_checkin import _ensure_employee

ME = "sl-me@example.com"
COLLEAGUE = "sl-colleague@example.com"
SICK = "SL Test Sick"
CHILD_SICK = "SL Test Child Sick"
OTHER = "SL Test Unpaid"


def _response(status):
	return SimpleNamespace(status_code=status, text="")


@unittest.skipUnless(frappe.db.exists("DocType", "Leave Application"), "HRMS is not installed")
class TestSickLeave(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (ME, COLLEAGUE):
			_ensure_user(user)
		_ensure_status_field()
		self.me = _ensure_employee(ME)
		self.colleague = _ensure_employee(COLLEAGUE)
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "SL Test Holidays",
				"from_date": "2025-01-01",
				"to_date": "2027-12-31",
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
		for employee in (self.me, self.colleague):
			frappe.db.set_value("Employee", employee, "holiday_list", holiday_list.name)
		for leave_type in (SICK, CHILD_SICK, OTHER):
			if not frappe.db.exists("Leave Type", leave_type):
				frappe.get_doc({"doctype": "Leave Type", "leave_type_name": leave_type, "is_lwp": 1}).insert(
					ignore_permissions=True
				)
		frappe.db.delete("Sick Leave Type Item", {"parent": sick_leave.SETTINGS})
		frappe.db.set_single_value("HR Settings", "restrict_backdated_leave_application", 0)
		for patcher in (
			patch.object(client.requests, "put", MagicMock(return_value=_response(201))),
			patch.object(client.requests, "delete", MagicMock(return_value=_response(204))),
			patch.object(client, "settings", lambda: SimpleNamespace(base_url="https://mail.example.com")),
			patch.object(client, "dav_password", lambda email: "pw"),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _configure(self, *leave_types):
		for idx, leave_type in enumerate(leave_types, start=1):
			frappe.get_doc(
				{
					"doctype": "Sick Leave Type Item",
					"parent": sick_leave.SETTINGS,
					"parenttype": sick_leave.SETTINGS,
					"parentfield": sick_leave.SETTINGS_FIELD,
					"idx": idx,
					"leave_type": leave_type,
				}
			).db_insert()

	def _leave(self, employee, leave_type, from_date, to_date, status="Approved", **values):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": employee,
				"leave_type": leave_type,
				"from_date": from_date,
				"to_date": to_date,
				"status": status,
				**values,
			}
		).insert(ignore_permissions=True)
		if status != "Open":
			doc.submit()
		return doc

	def test_nothing_configured_counts_nothing(self):
		self._leave(self.me, SICK, "2026-03-02", "2026-03-03")
		self.assertIsNone(sick_leave.get_sick_days([self.me], "2026-01-01", "2026-12-31"))

	def test_only_configured_types_count(self):
		self._configure(SICK, CHILD_SICK)
		self._leave(self.me, SICK, "2026-03-02", "2026-03-03")
		self._leave(self.me, CHILD_SICK, "2026-04-06", "2026-04-06")
		self._leave(self.me, OTHER, "2026-05-04", "2026-05-08")
		self.assertEqual(sick_leave.get_sick_days([self.me], "2026-01-01", "2026-12-31"), {self.me: 3})

	def test_only_approved_leave_counts(self):
		self._configure(SICK)
		self._leave(self.me, SICK, "2026-03-02", "2026-03-02")
		self._leave(self.me, SICK, "2026-03-09", "2026-03-10", status="Open")
		self._leave(self.me, SICK, "2026-03-16", "2026-03-17", status="Rejected")
		cancelled = self._leave(self.me, SICK, "2026-03-23", "2026-03-24")
		cancelled.cancel()
		self.assertEqual(sick_leave.get_sick_days([self.me], "2026-01-01", "2026-12-31"), {self.me: 1})

	def test_leave_across_new_year_is_clipped_and_half_days_count_half(self):
		self._configure(SICK)
		self._leave(self.me, SICK, "2025-12-30", "2026-01-02")
		self._leave(self.me, SICK, "2026-06-01", "2026-06-01", half_day=1, half_day_date="2026-06-01")
		self.assertEqual(sick_leave.get_sick_days([self.me], *sick_leave.year_bounds("2026-07-01")), {self.me: 2.5})
		self.assertEqual(sick_leave.get_sick_days([self.me], *sick_leave.year_bounds("2025-07-01")), {self.me: 2})

	def test_several_employees_in_one_call(self):
		self._configure(SICK)
		self._leave(self.me, SICK, "2026-03-02", "2026-03-03")
		self._leave(self.colleague, SICK, "2026-03-04", "2026-03-04")
		self.assertEqual(
			sick_leave.get_sick_days([self.me, self.colleague], "2026-01-01", "2026-12-31"),
			{self.me: 2, self.colleague: 1},
		)

	def test_my_leave_balance_shows_only_my_sick_days(self):
		frappe.set_user(ME)
		self.assertIsNone(personal_leave.get_my_leave_balance("2026-07-01")["sick_days"])

		frappe.set_user("Administrator")
		self._configure(SICK)
		self._leave(self.me, SICK, "2026-03-02", "2026-03-03")
		self._leave(self.colleague, SICK, "2026-03-04", "2026-03-06")
		frappe.set_user(ME)
		self.assertEqual(personal_leave.get_my_leave_balance("2026-07-01")["sick_days"], 2)

	def test_my_leave_balance_has_my_holidays_for_the_heatmap(self):
		holiday_list = frappe.get_doc("Holiday List", "SL Test Holidays")
		holiday_list.append("holidays", {"holiday_date": "2026-12-25", "description": "SL Test Christmas"})
		holiday_list.save(ignore_permissions=True)
		frappe.set_user(ME)
		holidays = personal_leave.get_my_leave_balance("2026-07-01")["holidays"]
		self.assertIn("SL Test Christmas", [h["description"] for h in holidays])
		self.assertTrue(all(str(h["date"]).startswith("2026-") for h in holidays))
