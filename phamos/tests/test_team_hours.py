# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit hours statistics (#1975): available hours, hour groups, rates, who sees whom."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import team_cockpit
from phamos.cockpits import team_hours, teams
from phamos.phamos import team_capacity_utils as utils
from phamos.tests.test_team_assignment import TEAM_A, TeamAssignmentTestCase

# November 2026: Monday 2nd to Friday 6th is one working week
WEEK = (date(2026, 11, 2), date(2026, 11, 6))


def _wwh(hours_per_day, valid_from=date(2026, 1, 1)):
	return frappe._dict(
		name="WWH",
		valid_from=valid_from,
		valid_to=None,
		hours={day: hours_per_day for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")},
	)


class TestAvailableHours(TeamAssignmentTestCase):
	def test_weekly_working_hours_count_per_day(self):
		with patch.object(utils, "_weekly_working_hours", return_value=[_wwh(8)]):
			self.assertEqual(team_hours.available_hours(self.anna, [WEEK]), (40, True))

	def test_contract_fallback_spreads_weekly_hours_over_monday_to_friday(self):
		contract = frappe._dict(effective_from=date(2026, 1, 1), valid_until=None, weekly_hours=30, fte_percentage=75)
		with patch.object(utils, "_contract_on", return_value=contract):
			self.assertEqual(team_hours.available_hours(self.anna, [(date(2026, 11, 2), date(2026, 11, 8))]), (30, True))
			self.assertEqual(team_hours.fte(self.anna, [WEEK]), 0.75)

	def test_neither_source_means_unknown(self):
		self.assertEqual(team_hours.available_hours(self.anna, [WEEK]), (0, False))

	def test_holidays_and_approved_leave_come_off(self):
		absences = {date(2026, 11, 2): 1, date(2026, 11, 3): 0.5}
		with patch.object(utils, "_weekly_working_hours", return_value=[_wwh(8)]), patch.object(
			team_hours, "_absences", return_value=absences
		):
			self.assertEqual(team_hours.available_hours(self.anna, [WEEK])[0], 28)

	def test_only_days_in_the_team_count(self):
		self.assign(self.anna, TEAM_A, "2026-11-04")
		frappe.local._team_capacity_cache = None  # the assignment's sync cached "no hours"
		with patch.object(utils, "_weekly_working_hours", return_value=[_wwh(8)]), patch.object(
			team_hours, "logged_hours", return_value=dict.fromkeys(team_hours.GROUPS, 0.0)
		):
			rows = team_hours.member_stats(TEAM_A, *WEEK)
		self.assertEqual([(r.employee, r.available) for r in rows], [(self.anna, 24)])


class TestHourGroups(FrappeTestCase):
	def test_three_signs_make_an_hour_internal(self):
		row = frappe._dict(project="P", internal_project=0, internal_customer=0, is_billable=1)
		self.assertEqual(team_hours.hour_group(row), "billable")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, is_billable=0)), "non_billable")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, internal_project=1)), "internal")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, internal_customer=1)), "internal")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, project=None)), "internal")

	def test_rates_leave_out_members_without_hours(self):
		rows = [
			frappe._dict(known=True, available=40, logged=30, billable=20, non_billable=5, internal=5, fte=1),
			frappe._dict(known=False, available=None, logged=10, billable=10, non_billable=0, internal=0, fte=0),
		]
		totals = team_hours.totals(rows)
		self.assertEqual(totals.booked_rate, 75)
		self.assertEqual(totals.billable_rate, 50)
		# the absolute totals still include everyone
		self.assertEqual(totals.logged, 40)
		# only members with a contract FTE: 30 h / 1 FTE, the other 10 h have no FTE
		self.assertEqual(totals.hours_per_fte, 30)


class TestLoggedHours(TeamAssignmentTestCase):
	def test_submitted_timesheet_rows_by_group(self):
		activity = frappe.get_all("Activity Type", limit=1, pluck="name")
		project = frappe.get_all("Project", filters={"customer": ["is", "set"]}, limit=1, pluck="name")
		if not (activity and project):
			self.skipTest("needs an Activity Type and a Project with a customer")
		company = frappe.db.get_value("Employee", self.anna, "company")
		timesheet = frappe.get_doc(
			{
				"doctype": "Timesheet",
				"employee": self.anna,
				"company": company,
				"time_logs": [
					{"activity_type": activity[0], "from_time": "2026-11-02 09:00:00", "hours": 3, "is_billable": 1, "project": project[0]},
					{"activity_type": activity[0], "from_time": "2026-11-03 09:00:00", "hours": 2, "is_billable": 0},
				],
			}
		).insert(ignore_permissions=True)
		internal = frappe.db.get_value("Project", project[0], "custom_is_internal_project") if frappe.db.has_column("Project", "custom_is_internal_project") else 0
		customer = frappe.db.get_value("Project", project[0], "customer")
		if internal or frappe.db.get_value("Customer", customer, "is_internal_customer"):
			self.skipTest("the first customer project is internal")
		# drafts count, as in the Team Capacity Overview and the Implementation (docstatus != 2)
		logged = team_hours.logged_hours(self.anna, [WEEK])
		self.assertEqual((logged["billable"], logged["internal"]), (3, 2))
		timesheet.submit()
		timesheet.cancel()
		self.assertEqual(sum(team_hours.logged_hours(self.anna, [WEEK]).values()), 0)


class TestWhoSeesWhat(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01")
		self.addCleanup(frappe.set_user, "Administrator")
		stub = patch.object(
			team_hours,
			"logged_hours",
			return_value=dict.fromkeys(team_hours.GROUPS, 0.0),
		)
		stub.start()
		self.addCleanup(stub.stop)

	def _rows_for(self, employee, setting):
		frappe.db.set_single_value("phamos Settings", team_cockpit.MEMBER_HOURS_SETTING, setting)
		user = frappe.db.get_value("Employee", employee, "user_id")
		frappe.set_user(user)
		with patch.object(teams, "require_active_team", return_value=TEAM_A), patch.object(
			team_cockpit, "check_app_permission", return_value=True
		):
			data = team_cockpit.get_hours_statistics()
		return {r.employee for r in data.windows["current"].members}, data

	def test_a_member_sees_only_their_own_row(self):
		self.assertEqual(self._rows_for(self.ben, 1)[0], {self.ben})

	def test_a_lead_sees_every_row_only_with_the_setting_on(self):
		self.assertEqual(self._rows_for(self.anna, 0)[0], {self.anna})
		self.assertEqual(self._rows_for(self.anna, 1)[0], {self.anna, self.ben})

	def test_missing_hours_notice_only_for_the_lead(self):
		self.assertEqual(self._rows_for(self.ben, 0)[1].missing_hours, [])
		names = {r["employee"] for r in self._rows_for(self.anna, 0)[1].missing_hours}
		self.assertEqual(names, {self.anna, self.ben})


class TestImplementations(FrappeTestCase):
	def test_no_currency_field_leaves_the_server(self):
		meta = frappe.get_meta("Implementation")
		currency_fields = {f.fieldname for f in meta.fields if f.fieldtype == "Currency"}
		self.assertFalse(currency_fields & set(team_cockpit.IMPLEMENTATION_FIELDS))
		self.assertTrue(all(meta.has_field(f) or f == "name" for f in team_cockpit.IMPLEMENTATION_FIELDS))
