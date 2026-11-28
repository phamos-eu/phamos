# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Assignment (#1974): membership with from/until, one team at a time, the Team follows."""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from phamos.cockpits import teams
from phamos.phamos import team_capacity_utils as utils
from phamos.phamos.doctype.team_assignment import team_assignment as ta

TEAM_A = "_Test Assignment Team A"
TEAM_B = "_Test Assignment Team B"
PREFIX = "team-assignment-test"


def _company():
	return "phamos" if frappe.db.exists("Company", "phamos") else frappe.db.get_value("Company", {}, "name")


class TeamAssignmentTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.addCleanup(frappe.db.rollback)
		self.addCleanup(lambda: setattr(frappe.local, "_team_capacity_cache", None))
		frappe.local._team_capacity_cache = None
		if not (_company() and frappe.db.get_value("Gender", {}, "name")):
			self.skipTest("needs a Company and a Gender")
		self.anna = self._employee("anna", "2020-01-01")
		self.ben = self._employee("ben", "2020-01-01")
		self.cara = self._employee("cara", "2026-06-01")
		for team in (TEAM_A, TEAM_B):
			if frappe.db.exists("Team", team):
				frappe.delete_doc("Team", team, force=True, ignore_permissions=True)
			frappe.get_doc({"doctype": "Team", "team_name": team}).insert(ignore_permissions=True)
		# no HR Addon records: hours come from what each test patches in
		hours = patch.object(utils, "_weekly_working_hours", return_value=[])
		hours.start()
		self.addCleanup(hours.stop)

	def _employee(self, key, joined):
		user = f"{PREFIX}-{key}@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({"doctype": "User", "email": user, "first_name": key.title(), "send_welcome_email": 0}).insert(
				ignore_permissions=True
			)
		existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
		if existing:
			frappe.db.set_value("Employee", existing, {"date_of_joining": joined, "status": "Active"})
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": key.title(),
					"gender": frappe.db.get_value("Gender", {}, "name"),
					"date_of_birth": "1990-01-01",
					"date_of_joining": joined,
					"company": _company(),
					"user_id": user,
					"create_user_permission": 0,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def assign(self, employee, team, from_date, until_date=None, role="Member"):
		return frappe.get_doc(
			{
				"doctype": "Team Assignment",
				"employee": employee,
				"team": team,
				"role": role,
				"from_date": from_date,
				"until_date": until_date,
			}
		).insert(ignore_permissions=True)


class TestRules(TeamAssignmentTestCase):
	def test_end_before_start_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.assign(self.anna, TEAM_A, "2026-03-01", "2026-02-01")

	def test_one_team_at_a_time_also_across_teams(self):
		first = self.assign(self.anna, TEAM_A, "2026-01-01")
		with self.assertRaises(frappe.ValidationError) as raised:
			self.assign(self.anna, TEAM_B, "2026-06-01")
		self.assertIn(first.name, str(raised.exception))
		# after ending the first one, the next team is fine
		first.until_date = "2026-05-31"
		first.save()
		self.assign(self.anna, TEAM_B, "2026-06-01")

	def test_one_lead_per_team_at_a_time(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", "2026-06-30", role="Lead")
		with self.assertRaises(frappe.ValidationError):
			self.assign(self.ben, TEAM_A, "2026-06-01", role="Lead")
		# a lead after the first one ended, and a co-lead alongside, are fine
		self.assign(self.ben, TEAM_A, "2026-07-01", role="Lead")
		self.assign(self.cara, TEAM_A, "2026-07-01", role="Co-Lead")

	def test_only_hr_management_and_system_manager_maintain_assignments(self):
		roles = {p.role for p in frappe.get_meta("Team Assignment").permissions if p.create and p.write}
		self.assertEqual(roles, {"HR Manager", "phamos General Management", "System Manager"})
		user = frappe.db.get_value("Employee", self.anna, "user_id")
		self.assertFalse(frappe.has_permission("Team Assignment", "create", user=user))


class TestTeamFollows(TeamAssignmentTestCase):
	def test_saving_rewrites_lead_co_lead_and_members(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01", role="Co-Lead")
		self.assign(self.cara, TEAM_A, "2026-06-01")
		team = frappe.get_doc("Team", TEAM_A)
		self.assertEqual(team.team_lead, self.anna)
		self.assertEqual(team.co_team_lead, self.ben)
		# everyone is a row, the lead too, so they count in the capacity
		self.assertEqual([row.employee for row in team.team_members], [self.anna, self.ben, self.cara])

	def test_an_ended_assignment_drops_out(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		ending = self.assign(self.ben, TEAM_A, "2026-01-01")
		ending.until_date = add_days(today(), -1)
		ending.save()
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_A).team_members], [self.anna])

	def test_deleting_an_assignment_drops_out(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		gone = self.assign(self.ben, TEAM_A, "2026-01-01")
		gone.delete(ignore_permissions=True)
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_A).team_members], [self.anna])

	def test_a_future_assignment_arrives_with_the_daily_job(self):
		self.assign(self.anna, TEAM_A, add_days(today(), 1))
		self.assertEqual(frappe.get_doc("Team", TEAM_A).team_members, [])
		ta.sync_team(TEAM_A, on_date=add_days(today(), 1))
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_A).team_members], [self.anna])

	def test_moving_to_another_team_updates_both(self):
		assignment = self.assign(self.anna, TEAM_A, "2026-01-01")
		assignment.team = TEAM_B
		assignment.save()
		self.assertEqual(frappe.get_doc("Team", TEAM_A).team_members, [])
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_B).team_members], [self.anna])

	def test_weekly_capacity_comes_from_weekly_working_hours(self):
		record = frappe._dict(
			name="WWH",
			valid_from=date(2026, 1, 1),
			valid_to=None,
			hours={"Monday": 8, "Tuesday": 8, "Wednesday": 8, "Thursday": 6, "Friday": 0},
		)
		with patch.object(utils, "_weekly_working_hours", return_value=[record]):
			self.assign(self.anna, TEAM_A, "2026-01-01")
		self.assertEqual(frappe.get_doc("Team", TEAM_A).team_members[0].weekly_capacity, 30)

	def test_weekly_capacity_falls_back_to_the_contract_then_zero(self):
		real_get_all = frappe.get_all

		def get_all(doctype, *args, **kwargs):
			if doctype == "Employment Contract":
				return [frappe._dict(weekly_hours=20)] if kwargs["filters"]["employee"] == self.anna else []
			return real_get_all(doctype, *args, **kwargs)

		with patch.object(utils.frappe, "get_all", side_effect=get_all):
			self.assertEqual(utils.get_employee_weekly_hours(self.anna, getdate(today())), 20)
			self.assertEqual(utils.get_employee_weekly_hours(self.ben, getdate(today())), 0)


class TestHelpers(TeamAssignmentTestCase):
	def test_members_of_a_past_date(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", "2026-03-31")
		self.assign(self.ben, TEAM_A, "2026-03-01")
		self.assertEqual(ta.members_of(TEAM_A, "2026-02-01"), [self.anna])
		self.assertEqual(ta.members_of(TEAM_A, "2026-03-15"), [self.anna, self.ben])
		self.assertEqual(ta.members_of(TEAM_A, "2026-05-01"), [self.ben])

	def test_members_between_cuts_periods_to_the_range(self):
		self.assign(self.anna, TEAM_A, "2026-01-15", "2026-02-10")
		periods = ta.members_between(TEAM_A, "2026-02-01", "2026-02-28")
		self.assertEqual(periods, {self.anna: [(date(2026, 2, 1), date(2026, 2, 10))]})

	def test_team_cockpit_access_follows_the_assignments(self):
		user = frappe.db.get_value("Employee", self.anna, "user_id")
		self.assertNotIn(TEAM_A, teams.member_teams(user))
		assignment = self.assign(self.anna, TEAM_A, "2026-01-01")
		self.assertEqual(teams.member_teams(user), [TEAM_A])
		assignment.until_date = add_days(today(), -1)
		assignment.save()
		self.assertNotIn(TEAM_A, teams.member_teams(user))
		# past dates still answer
		self.assertEqual(teams.member_teams(user, on_date="2026-02-01"), [TEAM_A])


class TestFromExistingTeams(TeamAssignmentTestCase):
	def _fill(self, team, created, lead=None, members=()):
		doc = frappe.get_doc("Team", team)
		doc.team_lead = lead
		for employee in members:
			doc.append("team_members", {"employee": employee})
		doc.save(ignore_permissions=True)
		# backdate the Team and its rows, as on a real site where the Team is older
		frappe.db.set_value("Team", team, "creation", created, update_modified=False)
		frappe.db.sql("update `tabTeam Members` set creation=%s where parent=%s", (created, team))
		return doc

	def _rows(self, names):
		return {
			(r.employee, r.team): r
			for r in frappe.get_all(
				"Team Assignment", filters={"name": ["in", names]}, fields=["employee", "team", "role", "from_date", "until_date"]
			)
		}

	def test_one_assignment_per_member_from_team_creation_or_joining(self):
		self._fill(TEAM_A, "2024-03-01", lead=self.anna, members=[self.ben, self.cara])
		rows = self._rows(ta.assignments_from_team(TEAM_A)["created"])
		self.assertEqual(rows[(self.anna, TEAM_A)].role, "Lead")
		self.assertEqual(rows[(self.ben, TEAM_A)].role, "Member")
		# ben joined the company before the Team existed: the Team's creation counts
		self.assertEqual(getdate(rows[(self.ben, TEAM_A)].from_date), date(2024, 3, 1))
		# cara joined later: her joining date counts
		self.assertEqual(getdate(rows[(self.cara, TEAM_A)].from_date), date(2026, 6, 1))
		self.assertTrue(all(r.until_date is None for r in rows.values()))

	def test_a_person_in_two_teams_keeps_the_one_with_the_higher_role(self):
		self._fill(TEAM_A, "2024-01-01", members=[self.anna])
		self._fill(TEAM_B, "2025-06-01", lead=self.anna, members=[self.ben])
		result = ta.assignments_from_teams([TEAM_A, TEAM_B])
		rows = self._rows(result["created"])
		self.assertIsNone(rows[(self.anna, TEAM_B)].until_date)
		# team A: ends the day before team B starts, so the history keeps it and nothing overlaps
		self.assertEqual(getdate(rows[(self.anna, TEAM_A)].until_date), date(2025, 5, 31))
		self.assertEqual(len(result["ended"]), 1)
		self.assertEqual(ta.members_of(TEAM_A, "2025-01-01"), [self.anna])
		self.assertEqual(ta.members_of(TEAM_B, today()), [self.anna, self.ben])

	def test_no_room_before_the_kept_team_means_no_assignment(self):
		self._fill(TEAM_A, "2025-06-01", members=[self.anna])
		self._fill(TEAM_B, "2025-06-01", members=[self.anna])
		result = ta.assignments_from_teams([TEAM_A, TEAM_B])
		# same role: the first team by name is kept; the other starts no earlier, so it is skipped
		self.assertEqual(result["skipped"], [f"{self.anna} in {TEAM_B}"])
		self.assertEqual(ta.members_of(TEAM_A, today()), [self.anna])

	def test_a_team_without_assignments_is_left_alone(self):
		self._fill(TEAM_A, "2024-01-01", members=[self.anna])
		ta.sync_all_teams()
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_A).team_members], [self.anna])
		user = frappe.db.get_value("Employee", self.anna, "user_id")
		self.assertIn(TEAM_A, teams.member_teams(user))


class TestSyncEdges(TeamAssignmentTestCase):
	def test_deleting_the_last_assignment_empties_the_team(self):
		only = self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		only.delete(ignore_permissions=True)
		team = frappe.get_doc("Team", TEAM_A)
		self.assertEqual((team.team_lead, team.team_members), (None, []))

	def test_becoming_lead_while_another_lead_is_open_is_refused(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		member = self.assign(self.ben, TEAM_A, "2026-01-01")
		member.role = "Lead"
		with self.assertRaises(frappe.ValidationError):
			member.save()

	def test_a_failing_team_does_not_block_the_assignment(self):
		with patch("phamos.phamos.doctype.team.team.Team.validate", side_effect=frappe.ValidationError("broken"), create=True):
			assignment = self.assign(self.anna, TEAM_A, "2026-01-01")
		self.assertTrue(frappe.db.exists("Team Assignment", assignment.name))
		self.assertEqual(frappe.get_doc("Team", TEAM_A).team_members, [])
		# the daily job catches up once the Team is fine again
		ta.sync_all_teams()
		self.assertEqual([row.employee for row in frappe.get_doc("Team", TEAM_A).team_members], [self.anna])


class TestConnections(FrappeTestCase):
	"""Team Assignments show on the Connections tab of the Team and of the Employee."""

	def test_team_shows_its_assignments(self):
		dashboard = frappe.get_meta("Team").get_dashboard_data()
		items = [item for group in dashboard.transactions for item in group["items"]]
		self.assertIn("Team Assignment", items)
		self.assertEqual(dashboard.fieldname, "team")

	def test_employee_shows_their_assignments(self):
		from phamos.custom_scripts.custom_python.employee_dashboard import get_employee_dashboard_data

		data = get_employee_dashboard_data({"transactions": []})
		self.assertIn("Team Assignment", data["transactions"][0]["items"])
