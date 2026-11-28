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
from phamos.phamos.doctype.team_assignment import team_assignment as ta
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
			days = team_hours.member_days(self.anna, [WEEK])
			self.assertTrue(all(d.fte == 0.75 for d in days.values()))

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
		periods = ta.members_between(TEAM_A, *WEEK)
		with patch.object(utils, "_weekly_working_hours", return_value=[_wwh(8)]):
			self.assertEqual(team_hours.available_hours(self.anna, periods[self.anna]), (24, True))


class TestHourGroups(FrappeTestCase):
	def test_three_signs_make_an_hour_internal(self):
		row = frappe._dict(project="P", internal_project=0, internal_customer=0, is_billable=1)
		self.assertEqual(team_hours.hour_group(row), "billable")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, is_billable=0)), "non_billable")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, internal_project=1)), "internal")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, internal_customer=1)), "internal")
		self.assertEqual(team_hours.hour_group(frappe._dict(row, project=None)), "internal")

	def test_rates_leave_out_days_without_hours(self):
		def day(available, known, fte, billable=0.0, non_billable=0.0, internal=0.0):
			return frappe._dict(available=available, known=known, fte=fte, billable=billable, non_billable=non_billable, internal=internal)

		# A: a whole working week known, 1.0 FTE, 30 h logged (20 billable)
		a_days = {date(2026, 11, 2 + i): day(8, True, 1, billable=4, internal=2) for i in range(5)}
		# B: hours unknown, no contract; 10 h logged
		b_days = {date(2026, 11, 2): day(0, False, 0, billable=10)}
		rows = [
			team_hours.member_row("A", "A", a_days, *WEEK),
			team_hours.member_row("B", "B", b_days, *WEEK),
		]
		totals = team_hours.totals(rows, 5)
		self.assertEqual((totals.booked_rate, totals.billable_rate), (75, 50))
		# the absolute totals still include everyone
		self.assertEqual(totals.logged, 40)
		# only hours on days with a contract FTE: 30 h / 1 FTE
		self.assertEqual(totals.hours_per_fte, 30)
		self.assertFalse(rows[1].known)

	def test_hours_per_fte_weights_part_period_members(self):
		def day(fte, hours):
			return frappe._dict(available=8, known=True, fte=fte, billable=hours, non_billable=0.0, internal=0.0)

		# A in the team all 30 days, B (also 1.0 FTE) only the last 6 days
		a_days = {date(2026, 11, i): day(1, 5) for i in range(1, 31)}
		b_days = {date(2026, 11, i): day(1, 3) for i in range(25, 31)}
		rows = [
			team_hours.member_row("A", "A", a_days, date(2026, 11, 1), date(2026, 11, 30)),
			team_hours.member_row("B", "B", b_days, date(2026, 11, 1), date(2026, 11, 30)),
		]
		totals = team_hours.totals(rows, 30)
		# 168 h over 1.2 FTE, not over 2
		self.assertEqual((totals.fte, totals.hours_per_fte), (1.2, 140))


class TestPeriods(FrappeTestCase):
	def test_windows_compare_the_same_days(self):
		w = team_hours.month_windows(date(2026, 3, 31))
		self.assertEqual(w["current"], (date(2026, 3, 1), date(2026, 3, 31)))
		# February has no 31st: the whole February
		self.assertEqual(w["previous"], (date(2026, 2, 1), date(2026, 2, 28)))
		self.assertEqual(w["last_year"], (date(2025, 3, 1), date(2025, 3, 31)))

	def test_leap_day(self):
		w = team_hours.month_windows(date(2028, 2, 29))
		self.assertEqual(w["previous"], (date(2028, 1, 1), date(2028, 1, 29)))
		self.assertEqual(w["last_year"], (date(2027, 2, 1), date(2027, 2, 28)))
		self.assertEqual(team_hours.same_day_last_year(date(2028, 2, 29)), date(2027, 2, 28))


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
		logged = team_hours._logged_by_day(self.anna, *WEEK)
		self.assertEqual(logged[date(2026, 11, 2)]["billable"], 3)
		self.assertEqual(logged[date(2026, 11, 3)]["internal"], 2)
		timesheet.submit()
		timesheet.cancel()
		self.assertEqual(team_hours._logged_by_day(self.anna, *WEEK), {})


class TestWhoSeesWhat(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01")
		self.addCleanup(frappe.set_user, "Administrator")
		stub = patch.object(team_hours, "_logged_by_day", return_value={})
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


class TestAbsences(FrappeTestCase):
	def test_half_day_and_holiday_inside_leave(self):
		holidays = [date(2026, 11, 4)]
		leave = frappe._dict(
			from_date=date(2026, 10, 30), to_date=date(2026, 11, 5), half_day=1, half_day_date=date(2026, 11, 5), leave_type="X"
		)
		real_get_all = frappe.get_all

		def get_all(doctype, *args, **kwargs):
			if doctype == "Holiday":
				return holidays
			if doctype == "Leave Application":
				return [leave]
			return real_get_all(doctype, *args, **kwargs)

		with patch.object(utils, "employee_holiday_list", return_value="HL"), patch.object(
			team_hours.frappe, "get_all", side_effect=get_all
		):
			absent = team_hours._absences("EMP", *WEEK)
		# the leave started before the period: only its days inside count
		self.assertNotIn(date(2026, 10, 30), absent)
		self.assertEqual(absent[date(2026, 11, 2)], 1)
		# the holiday inside the leave counts once, as a whole day
		self.assertEqual(absent[date(2026, 11, 4)], 1)
		# only the half day is halved
		self.assertEqual(absent[date(2026, 11, 5)], 0.5)


class TestImplementationsEndpoint(TeamAssignmentTestCase):
	def test_a_user_without_a_team_is_refused(self):
		frappe.set_user(frappe.db.get_value("Employee", self.anna, "user_id"))
		self.addCleanup(frappe.set_user, "Administrator")
		with patch.object(team_cockpit, "check_app_permission", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				team_cockpit.get_team_implementations()

	def test_only_the_teams_implementations_and_no_currency(self):
		name = frappe.get_all("Implementation", filters={"status": ["not in", ["Cancelled", "Completed"]]}, limit=1, pluck="name")
		if not name:
			self.skipTest("needs an open Implementation")
		frappe.db.set_value("Implementation", name[0], "team", TEAM_A, update_modified=False)
		with patch.object(teams, "require_active_team", return_value=TEAM_A):
			data = team_cockpit.get_team_implementations()
		self.assertEqual([r.name for r in data["implementations"]], [name[0]])
		currency = {f.fieldname for f in frappe.get_meta("Implementation").fields if f.fieldtype == "Currency"}
		self.assertFalse(currency & set(data["implementations"][0].keys()))
		self.assertEqual(len(data["implementations"][0].months), 6)
