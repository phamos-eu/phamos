# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employees list in the Human Resources Cockpit (phamos/phamos#1835).

Runs as HR User and HR Manager, so the access rules of #1833 really apply. The employees'
names start with "he-", and every call searches for that, so other employees on the site
don't get in the way. SOGo is patched out, because every Leave Application is mirrored as
a calendar Event (milestone 68, Phase 2).
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, nowdate

from phamos.api import hr_employees
from phamos.mailcow_integration.caldav import client
from phamos.phamos.hr import sick_leave
from phamos.tests.test_personal_checkin import _ensure_employee

ANNA = "he-anna@example.com"
BEN = "he-ben@example.com"
CARL = "he-carl@example.com"
HR_USER = "he-hr-user@example.com"
HR_MANAGER = "he-hr-manager@example.com"
NOBODY = "he-nobody@example.com"
ANNUAL = "HE Test Annual"
SPECIAL = "HE Test Special"
SICK = "HE Test Sick"


def _ensure_user(email):
	"""version-15 has no test_mailcow_sync_event; same helper: a user with the Employee role."""
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")


def _response(status):
	return SimpleNamespace(status_code=status, text="")


@unittest.skipUnless(frappe.db.exists("DocType", "Leave Application"), "HRMS is not installed")
class TestHrEmployees(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (ANNA, BEN, CARL, HR_USER, HR_MANAGER, NOBODY):
			_ensure_user(user)
			frappe.get_doc("User", user).remove_roles("System Manager", "HR Manager", "HR User")
		frappe.get_doc("User", HR_USER).add_roles("HR User")
		frappe.get_doc("User", HR_MANAGER).add_roles("HR Manager")
		self.today = getdate(nowdate())
		self.year_start = self.today.replace(month=1, day=1)
		self.year_end = self.today.replace(month=12, day=31)
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "HE Test Holidays",
				"from_date": add_days(self.year_start, -400),
				"to_date": add_days(self.year_end, 400),
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
		self.anna, self.ben, self.carl = (_ensure_employee(u) for u in (ANNA, BEN, CARL))
		for employee in (self.anna, self.ben, self.carl):
			frappe.db.set_value(
				"Employee",
				employee,
				{"holiday_list": holiday_list.name, "date_of_joining": "2020-01-01", "date_of_birth": "1990-05-17"},
			)
		for leave_type, lwp in ((ANNUAL, 0), (SPECIAL, 0), (SICK, 1)):
			if not frappe.db.exists("Leave Type", leave_type):
				frappe.get_doc({"doctype": "Leave Type", "leave_type_name": leave_type, "is_lwp": lwp}).insert(
					ignore_permissions=True
				)
		frappe.db.delete("Sick Leave Type Item", {"parent": sick_leave.SETTINGS})
		frappe.get_doc(
			{
				"doctype": "Sick Leave Type Item",
				"parent": sick_leave.SETTINGS,
				"parenttype": sick_leave.SETTINGS,
				"parentfield": sick_leave.SETTINGS_FIELD,
				"idx": 1,
				"leave_type": SICK,
			}
		).db_insert()
		frappe.db.set_single_value("HR Settings", "restrict_backdated_leave_application", 0)
		for employee in (self.anna, self.ben, self.carl):
			self._allocate(employee, ANNUAL, 30)
		self._allocate(self.anna, SPECIAL, 2)
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

	def _allocate(self, employee, leave_type, days):
		frappe.get_doc(
			{
				"doctype": "Leave Allocation",
				"employee": employee,
				"leave_type": leave_type,
				"from_date": self.year_start,
				"to_date": self.year_end,
				"new_leaves_allocated": days,
			}
		).insert(ignore_permissions=True).submit()

	def _leave(self, employee, leave_type, from_date, to_date, status="Approved"):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": employee,
				"leave_type": leave_type,
				"from_date": from_date,
				"to_date": to_date,
				"status": status,
			}
		).insert(ignore_permissions=True)
		if status != "Open":
			doc.submit()
		return doc

	def _list(self, user, **kwargs):
		frappe.set_user(user)
		try:
			return hr_employees.get_employees(search="he-", **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _row(self, result, employee):
		return next(r for r in result["employees"] if r["employee"] == employee)

	def test_user_without_hr_role_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._list(NOBODY)

	def test_only_hr_manager_gets_sick_days(self):
		self._leave(self.anna, SICK, self.year_start, add_days(self.year_start, 1))
		as_user = self._list(HR_USER)
		self.assertFalse(as_user["can_see_sick_days"])
		self.assertNotIn("sick_days", self._row(as_user, self.anna))
		as_manager = self._list(HR_MANAGER)
		self.assertTrue(as_manager["can_see_sick_days"])
		self.assertEqual(self._row(as_manager, self.anna)["sick_days"], 2)

	def test_birthday_has_no_year(self):
		self.assertEqual(self._row(self._list(HR_USER), self.anna)["birthday"], "05-17")

	def test_leave_per_type_without_sick_leave(self):
		self._leave(self.anna, ANNUAL, self.year_start, add_days(self.year_start, 2))
		self._leave(self.anna, SICK, add_days(self.year_start, 7), add_days(self.year_start, 7))
		result = self._list(HR_USER)
		leave = self._row(result, self.anna)["leave"]
		self.assertEqual(leave[ANNUAL], {"allocated": 30, "taken": 3, "left": 27})
		self.assertEqual(leave[SPECIAL], {"allocated": 2, "taken": 0, "left": 2})
		self.assertNotIn(SICK, leave)
		self.assertNotIn(SICK, result["leave_types"])
		# three employees have the annual type, one the special type
		self.assertEqual([t for t in result["leave_types"] if t in (ANNUAL, SPECIAL)], [ANNUAL, SPECIAL])

	def test_last_next_and_pending_leave_ignore_sick_leave(self):
		self._leave(self.ben, ANNUAL, self.year_start, self.year_start)
		self._leave(self.ben, SICK, add_days(self.today, -1), add_days(self.today, -1))
		self._leave(self.ben, SICK, add_days(self.today, 10), add_days(self.today, 10))
		self._leave(self.ben, SICK, add_days(self.today, 20), add_days(self.today, 20), status="Open")
		row = self._row(self._list(HR_USER), self.ben)
		self.assertEqual(getdate(row["last_leave"]), self.year_start)
		self.assertIsNone(row["next_leave"])
		self.assertEqual(row["pending_count"], 0)

	def test_next_leave_and_pending_count(self):
		self._leave(self.ben, ANNUAL, add_days(self.today, 10), add_days(self.today, 11))
		self._leave(self.ben, ANNUAL, add_days(self.today, 30), add_days(self.today, 30), status="Open")
		row = self._row(self._list(HR_USER), self.ben)
		self.assertEqual(getdate(row["next_leave"]), add_days(self.today, 10))
		self.assertEqual(row["pending_count"], 1)

	def test_contract_values_only_with_contract_access(self):
		as_user = self._list(HR_USER)
		self.assertFalse(as_user["can_see_contracts"])
		self.assertNotIn("fte_percentage", self._row(as_user, self.anna))
		as_manager = self._list(HR_MANAGER)
		self.assertTrue(as_manager["can_see_contracts"])
		self.assertIn("fte_percentage", self._row(as_manager, self.anna))

	def _detail(self, user, employee):
		frappe.set_user(user)
		try:
			return hr_employees.get_employee(employee)
		finally:
			frappe.set_user("Administrator")

	def test_detail_lists_this_years_applications_without_sick_leave(self):
		self._leave(self.anna, ANNUAL, self.year_start, add_days(self.year_start, 1))
		self._leave(self.anna, ANNUAL, add_days(self.today, 5), add_days(self.today, 5), status="Open")
		rejected = self._leave(self.anna, ANNUAL, add_days(self.year_start, 10), add_days(self.year_start, 10), status="Rejected")
		self._leave(self.anna, SICK, add_days(self.year_start, 20), add_days(self.year_start, 20))
		cancelled = self._leave(self.anna, ANNUAL, add_days(self.year_start, 30), add_days(self.year_start, 30))
		cancelled.cancel()
		detail = self._detail(HR_USER, self.anna)
		applications = detail["applications"]
		self.assertCountEqual([a.status for a in applications], ["Open", "Cancelled", "Rejected", "Approved"])
		self.assertIn(cancelled.name, [a.name for a in applications])
		self.assertIn(rejected.name, [a.name for a in applications])
		self.assertNotIn(SICK, [a.leave_type for a in applications])
		self.assertEqual(detail["leave"][ANNUAL]["taken"], 2)

	def test_detail_has_this_years_holidays_for_the_heatmap(self):
		holiday_list = frappe.db.get_value("Employee", self.anna, "holiday_list")
		doc = frappe.get_doc("Holiday List", holiday_list)
		doc.append("holidays", {"holiday_date": self.today.replace(month=12, day=25), "description": "HE Test Holiday"})
		doc.save(ignore_permissions=True)
		holidays = self._detail(HR_USER, self.anna)["holidays"]
		self.assertIn("HE Test Holiday", [h["description"] for h in holidays])
		self.assertTrue(all(self.year_start <= getdate(h["date"]) <= self.year_end for h in holidays))

	def test_detail_access_rules_match_the_list(self):
		self._leave(self.anna, SICK, self.year_start, self.year_start)
		as_user = self._detail(HR_USER, self.anna)
		self.assertNotIn("sick_days", as_user)
		self.assertNotIn("contract", as_user)
		as_manager = self._detail(HR_MANAGER, self.anna)
		self.assertEqual(as_manager["sick_days"], 1)
		self.assertIn("contract", as_manager)
		with self.assertRaises(frappe.PermissionError):
			self._detail(NOBODY, self.anna)

	def test_detail_contract_has_leave_fields_but_no_salary(self):
		company = frappe.db.get_value("Employee", self.anna, "company")
		frappe.get_doc(
			{
				"doctype": "Employment Contract",
				"employee": self.anna,
				"company": company,
				"contract_type": "Employed",
				"effective_from": self.year_start,
				"currency": frappe.get_cached_value("Company", company, "default_currency"),
				"fte_percentage": 80,
				"working_days_per_week": 4,
				"yearly_gross_full_time": 60000,
			}
		).insert(ignore_permissions=True).submit()
		contract = self._detail(HR_MANAGER, self.anna)["contract"]
		self.assertEqual(contract["fte_percentage"], 80)
		self.assertEqual(contract["leave_days_per_year"], 24)
		self.assertFalse({"monthly_gross", "yearly_gross_full_time", "base_monthly_gross"} & set(contract))

	def test_detail_respects_user_permissions_like_the_list(self):
		frappe.get_doc(
			{"doctype": "User Permission", "user": HR_USER, "allow": "Employee", "for_value": self.anna}
		).insert(ignore_permissions=True)
		self.assertEqual([r["employee"] for r in self._list(HR_USER)["employees"]], [self.anna])
		self.assertEqual(self._detail(HR_USER, self.anna)["employee"], self.anna)
		with self.assertRaises(frappe.PermissionError):
			self._detail(HR_USER, self.ben)

	def test_detail_of_unknown_employee_is_an_error(self):
		with self.assertRaises(frappe.DoesNotExistError):
			self._detail(HR_USER, "HE-DOES-NOT-EXIST")

	def test_leavers_only_with_the_left_filter_and_counted_to_their_relieving_date(self):
		frappe.db.set_value("Employee", self.carl, {"status": "Left", "relieving_date": "2025-01-01"})
		active = self._list(HR_USER)
		self.assertNotIn(self.carl, [r["employee"] for r in active["employees"]])
		left = self._list(HR_USER, status="Left")
		self.assertEqual([r["employee"] for r in left["employees"]], [self.carl])
		self.assertEqual(self._row(left, self.carl)["years_in_company"], 5)
