# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Calendar in the Human Resources Cockpit (phamos/phamos#1838).

Reuses the fixtures of the Employees list tests (employees "he-…", leave types, SOGo patched
out) and checks the calendar's own rules: neutral absences, requests, birthdays, holidays.
"""

import unittest

import frappe
from frappe.utils import add_days, getdate

from phamos.api import hr_team_calendar
from phamos.tests.test_hr_employees import ANNUAL, HR_MANAGER, HR_USER, NOBODY, SICK, HrEmployeesFixture


@unittest.skipUnless(frappe.db.exists("DocType", "Leave Application"), "HRMS is not installed")
class TestHrTeamCalendar(HrEmployeesFixture):
	def setUp(self):
		super().setUp()
		self.holiday_list = frappe.db.get_value("Employee", self.anna, "holiday_list")
		self.start = self.year_start
		self.end = self.year_end

	def _calendar(self, user, start=None, end=None):
		frappe.set_user(user)
		try:
			return hr_team_calendar.get_team_calendar(start or self.start, end or self.end)
		finally:
			frappe.set_user("Administrator")

	def _absences(self, result, employee):
		return [a for a in result["absences"] if a["employee"] == employee]

	def test_user_without_hr_role_is_refused(self):
		with self.assertRaises(frappe.PermissionError):
			self._calendar(NOBODY)

	def test_range_is_checked(self):
		with self.assertRaises(frappe.ValidationError):
			self._calendar(HR_USER, self.end, self.start)
		with self.assertRaises(frappe.ValidationError):
			self._calendar(HR_USER, self.start, add_days(self.start, hr_team_calendar.MAX_DAYS + 1))

	def test_absences_are_neutral_for_every_role(self):
		self._leave(self.anna, ANNUAL, self.year_start, add_days(self.year_start, 1))
		self._leave(self.anna, SICK, add_days(self.year_start, 7), add_days(self.year_start, 7))
		for user in (HR_USER, HR_MANAGER):
			absences = self._absences(self._calendar(user), self.anna)
			# sick leave is there too, and nothing says which one it is
			self.assertEqual(len(absences), 2)
			for absence in absences:
				self.assertNotIn("leave_type", absence)
				self.assertNotIn("description", absence)
				self.assertNotIn("name", absence)

	def test_requests_are_marked_and_rejected_left_out(self):
		approved = self._leave(self.ben, ANNUAL, self.year_start, self.year_start)
		requested = self._leave(self.ben, ANNUAL, add_days(self.year_start, 3), add_days(self.year_start, 3), "Open")
		self._leave(self.ben, ANNUAL, add_days(self.year_start, 5), add_days(self.year_start, 5), "Rejected")
		absences = self._absences(self._calendar(HR_USER), self.ben)
		self.assertEqual(
			[(getdate(a["from_date"]), a["requested"]) for a in absences],
			[(getdate(approved.from_date), False), (getdate(requested.from_date), True)],
		)

	def test_absences_outside_the_range_are_left_out(self):
		self._leave(self.carl, ANNUAL, self.year_start, self.year_start)
		result = self._calendar(HR_USER, add_days(self.year_start, 1), add_days(self.year_start, 30))
		self.assertEqual(self._absences(result, self.carl), [])

	def test_birthdays_have_no_year_of_birth(self):
		result = self._calendar(HR_USER)
		birthdays = [b["date"] for b in result["birthdays"] if b["employee"] == self.anna]
		self.assertEqual(birthdays, [getdate(f"{self.today.year}-05-17")])
		self.assertNotIn("date_of_birth", next(e for e in result["employees"] if e["employee"] == self.anna))

	def test_birthday_on_29_february(self):
		days = hr_team_calendar._birthdays_between(getdate("2000-02-29"), getdate("2027-01-01"), getdate("2028-12-31"))
		self.assertEqual(days, [getdate("2027-02-28"), getdate("2028-02-29")])

	def test_holidays_carry_the_country_and_weekly_offs_stay_apart(self):
		holiday_list = frappe.get_doc("Holiday List", self.holiday_list)
		holiday_list.country = "Germany"
		holiday_list.holidays = []
		holiday_list.append("holidays", {"holiday_date": add_days(self.year_start, 2), "description": "<p>Test Day</p>"})
		holiday_list.append(
			"holidays", {"holiday_date": add_days(self.year_start, 4), "description": "Weekly Off", "weekly_off": 1}
		)
		holiday_list.save(ignore_permissions=True)

		entry = self._calendar(HR_USER)["holiday_lists"][self.holiday_list]
		self.assertEqual(entry["country_code"], "DE")
		self.assertEqual(entry["holidays"], [{"date": add_days(self.year_start, 2), "description": "Test Day"}])
		self.assertEqual([getdate(d) for d in entry["weekly_offs"]], [add_days(self.year_start, 4)])

	def test_respects_user_permissions(self):
		frappe.get_doc(
			{"doctype": "User Permission", "user": HR_USER, "allow": "Employee", "for_value": self.anna}
		).insert(ignore_permissions=True)
		self._leave(self.ben, ANNUAL, self.year_start, self.year_start)
		result = self._calendar(HR_USER)
		self.assertEqual([e["employee"] for e in result["employees"]], [self.anna])
		self.assertEqual(self._absences(result, self.ben), [])
