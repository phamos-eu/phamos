# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team capacity (#1983): scheduled hours come from the Weekly Working Hours valid on the day, and
the weekly team capacity subtracts the leave and holidays of the whole week."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_last_day, getdate

from phamos.phamos import team_capacity_utils as utils
from phamos.phamos.doctype.team import team as team_module

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
EMPLOYEE_USER = "team-capacity-member@example.com"
HOLIDAY_LIST = "_Test Team Capacity Holidays"
TEAM = "_Test Team Capacity"


def _record(valid_from, valid_to, hours):
	return frappe._dict(
		name=f"WWH {valid_from}",
		valid_from=valid_from,
		valid_to=valid_to,
		hours={day: hours for day in WEEKDAYS},
	)


def _clear_cache():
	frappe.local._team_capacity_cache = None


class TestDailyHours(FrappeTestCase):
	def setUp(self):
		_clear_cache()

	def tearDown(self):
		_clear_cache()

	def test_the_record_valid_on_the_day_counts(self):
		records = [_record(date(2026, 7, 1), date(2026, 12, 31), 6), _record(date(2026, 1, 1), date(2026, 6, 30), 8)]
		with patch.object(utils, "_weekly_working_hours", return_value=records):
			self.assertEqual(utils.get_employee_daily_hours("EMP-1", date(2026, 3, 2)), 8)  # Monday
			self.assertEqual(utils.get_employee_daily_hours("EMP-1", date(2026, 9, 7)), 6)  # Monday
			# a Saturday has no row
			self.assertEqual(utils.get_employee_daily_hours("EMP-1", date(2026, 9, 5)), 0)
			# outside every validity: no scheduled hours
			self.assertEqual(utils.get_employee_daily_hours("EMP-1", date(2027, 1, 4)), 0)

	def test_team_and_overview_use_the_same_lookup(self):
		records = [_record(date(2026, 1, 1), date(2026, 12, 31), 7)]
		with patch.object(utils, "_weekly_working_hours", return_value=records):
			self.assertEqual(team_module.get_employee_working_hours("EMP-2", date(2026, 3, 3)), 7)

	def test_no_hr_addon_means_no_hours(self):
		with patch.object(frappe.db, "exists", return_value=False):
			self.assertEqual(utils._weekly_working_hours("EMP-3"), [])


class TestWeeklyTeamCapacity(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_clear_cache()
		if frappe.db.exists("Holiday List", HOLIDAY_LIST):
			frappe.delete_doc("Holiday List", HOLIDAY_LIST, force=True)
		frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": HOLIDAY_LIST,
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				# Monday 29 June (the week of 1 July starts in June) and Monday 16 November
				"holidays": [
					{"holiday_date": "2026-06-29", "description": "Test holiday June"},
					{"holiday_date": "2026-11-16", "description": "Test holiday November"},
				],
			}
		).insert(ignore_permissions=True)
		self.employee = self._employee()
		if frappe.db.exists("Team", TEAM):
			frappe.delete_doc("Team", TEAM, force=True, ignore_permissions=True)
		self.team = frappe.get_doc(
			{
				"doctype": "Team",
				"team_name": TEAM,
				"team_members": [{"employee": self.employee, "weekly_capacity": 40}],
			}
		).insert(ignore_permissions=True)
		self.records = patch.object(
			utils, "_weekly_working_hours", return_value=[_record(date(2026, 1, 1), date(2026, 12, 31), 8)]
		)
		self.records.start()

	def tearDown(self):
		self.records.stop()
		_clear_cache()
		frappe.db.rollback()

	def _employee(self):
		if not frappe.db.exists("User", EMPLOYEE_USER):
			frappe.get_doc(
				{"doctype": "User", "email": EMPLOYEE_USER, "first_name": "Capacity", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		existing = frappe.db.get_value("Employee", {"user_id": EMPLOYEE_USER}, "name")
		if existing:
			frappe.db.set_value("Employee", existing, "holiday_list", HOLIDAY_LIST)
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": "Capacity",
					"gender": frappe.db.get_value("Gender", {}, "name"),
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": frappe.db.get_value("Company", {}, "name"),
					"user_id": EMPLOYEE_USER,
					"create_user_permission": 0,
					"holiday_list": HOLIDAY_LIST,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _refresh(self, today):
		week_start, week_end = team_module.get_week_bounds(today)
		month_start, month_end = today.replace(day=1), getdate(get_last_day(today))
		team_module.refresh_team_capacity(self.team, today, month_start, month_end, week_start, week_end)
		return self.team

	def test_a_holiday_earlier_in_the_week_counts(self):
		# Wednesday 18 November; the holiday was on Monday. Before #1983 only today's leave counted.
		team = self._refresh(date(2026, 11, 18))
		self.assertEqual(team.total_team_capacity, 32)
		# today itself is a normal day
		self.assertEqual(team.total_team_capacity_daily, 8)

	def test_a_holiday_in_the_previous_month_of_the_same_week_counts(self):
		# Wednesday 1 July; the week started on Monday 29 June, outside the month's leave rows
		team = self._refresh(date(2026, 7, 1))
		self.assertEqual(team.total_team_capacity, 32)
		self.assertNotIn(date(2026, 6, 29), [row.date for row in team.team_member_leaves_and_holiday])
