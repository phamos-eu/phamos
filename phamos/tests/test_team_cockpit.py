# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The Team Cockpit (#1955): wired like the department cockpits, but scoped to the session user's
active Team, which the server resolves from their membership."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from phamos.api import software_development_spa
from phamos.api import team_cockpit as tc
from phamos.cockpits import teams
from phamos.cockpits.settings import COCKPITS, COCKPIT_SETTINGS
from phamos.cockpits.setup import ensure_issue_fields, ensure_task_fields
from phamos.setup.general_management import GENERAL_MANAGEMENT_ROLE
from phamos.www import spa_boot
from phamos.www import team_cockpit as page

ROUTE = "/team-cockpit"
ALPHA = "_Test Team Alpha"
BETA = "_Test Team Beta"
LEAD = "team-cockpit-lead@example.com"
CO_LEAD = "team-cockpit-co-lead@example.com"
MEMBER = "team-cockpit-member@example.com"
BOTH = "team-cockpit-both@example.com"
OUTSIDER = "team-cockpit-outsider@example.com"
MANAGER = "team-cockpit-manager@example.com"
ROLES = ["Projects User", "Support Team"]


def _whitelisted(module):
	return {name: fn for name, fn in vars(module).items() if callable(fn) and fn in frappe.whitelisted}


def _make_user(email, roles=ROLES):
	"""A System User with exactly `roles` (plus the automatic ones)."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.remove_roles(*[r.role for r in user.roles])
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	user.add_roles(*roles)
	return email


def _make_employee(user):
	existing = frappe.db.get_value("Employee", {"user_id": user}, "name")
	if existing:
		return existing
	return (
		frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": user.split("@")[0],
				"gender": frappe.db.get_value("Gender", {}, "name"),
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2020-01-01",
				"company": frappe.db.get_value("Company", {}, "name"),
				"user_id": user,
				# no automatic User Permission on the Employee: it would hide records by company
				"create_user_permission": 0,
				"status": "Active",
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _make_team(name, lead=None, co_lead=None, members=()):
	if frappe.db.exists("Team", name):
		frappe.delete_doc("Team", name, force=True, ignore_permissions=True)
	return frappe.get_doc(
		{
			"doctype": "Team",
			"team_name": name,
			"team_lead": lead,
			"co_team_lead": co_lead,
			"team_members": [{"employee": employee} for employee in members],
		}
	).insert(ignore_permissions=True)


class TeamCockpitTestCase(FrappeTestCase):
	"""Two teams: Alpha (lead, co-lead, member, both) and Beta (both). The outsider is in none."""

	def setUp(self):
		frappe.set_user("Administrator")
		ensure_task_fields()
		ensure_issue_fields()
		employees = {
			user: _make_employee(_make_user(user)) for user in (LEAD, CO_LEAD, MEMBER, BOTH, OUTSIDER)
		}
		_make_user(MANAGER, [GENERAL_MANAGEMENT_ROLE])
		_make_team(ALPHA, employees[LEAD], employees[CO_LEAD], [employees[MEMBER], employees[BOTH]])
		_make_team(BETA, members=[employees[BOTH]])
		for user in (LEAD, CO_LEAD, MEMBER, BOTH, OUTSIDER, MANAGER):
			frappe.defaults.clear_user_default(teams.ACTIVE_TEAM_KEY, user=user)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def issue(self, subject, team=None):
		return frappe.get_doc(
			{"doctype": "Issue", "subject": subject, "custom_team": team}
		).insert(ignore_permissions=True)

	def task(self, subject, team=None):
		return frappe.get_doc(
			{"doctype": "Task", "subject": subject, "custom_team": team}
		).insert(ignore_permissions=True)


class TestTeamCockpitWiring(FrappeTestCase):
	def test_exposes_the_same_endpoints_as_software_development(self):
		# The shared spa_shared views call these by name, so a missing one breaks a screen.
		expected = {
			name.replace("get_software_development_settings", tc.CONFIG.settings_method_name)
			for name in _whitelisted(software_development_spa)
		}
		own = {"get_teams", "set_active_team"}
		self.assertEqual(set(_whitelisted(tc)), expected | own)

	def test_every_endpoint_checks_access(self):
		ungated = [name for name, fn in _whitelisted(tc).items() if not getattr(fn, "requires_team", False)]
		self.assertEqual(ungated, [])

	def test_window_colour_and_settings_tab(self):
		self.assertEqual(COCKPITS[ROUTE], ("team", "#1d4ed8"))
		meta = frappe.get_meta(COCKPIT_SETTINGS)
		for field in ("team_cockpit_tab", "team_open_cockpit", "team_color", "team_glow"):
			self.assertTrue(meta.has_field(field), field)
		# a team is not picked in Cockpit Settings: it follows the user
		self.assertFalse(meta.has_field("team_department"))

	def test_team_field_on_issue_and_task(self):
		ensure_task_fields()
		ensure_issue_fields()
		for doctype in ("Issue", "Task"):
			frappe.clear_cache(doctype=doctype)
			field = frappe.get_meta(doctype).get_field("custom_team")
			self.assertEqual((field.fieldtype, field.options, field.reqd), ("Link", "Team", 0), doctype)
		# on Issue the field must not sit in Phriend's section, which hides on most Issues
		self.assertEqual(frappe.get_meta("Issue").get_field("custom_team").insert_after, "custom_department")


class TestTeamCockpitAccess(TeamCockpitTestCase):
	def test_lead_co_lead_and_member_get_in(self):
		for user in (LEAD, CO_LEAD, MEMBER):
			frappe.set_user(user)
			self.assertTrue(tc.check_app_permission(), user)
			self.assertEqual(tc.get_teams(), {"teams": [{"name": ALPHA}], "active": ALPHA}, user)

	def test_a_user_in_no_team_stays_out(self):
		frappe.set_user(OUTSIDER)
		self.assertTrue(frappe.has_permission("Task", "read"))

		self.assertFalse(tc.check_app_permission())
		with self.assertRaises(frappe.PermissionError):
			tc.get_teams()
		with self.assertRaises(frappe.PermissionError):
			tc.get_tasks()
		with self.assertRaises(frappe.PermissionError):
			page.get_context(frappe._dict())

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		self.assertFalse(tc.check_app_permission())

	def test_general_management_opens_every_team(self):
		frappe.set_user(MANAGER)
		names = [team["name"] for team in tc.get_teams()["teams"]]
		self.assertIn(ALPHA, names)
		self.assertIn(BETA, names)

	def test_an_inactive_employee_is_no_member(self):
		frappe.db.set_value("Employee", {"user_id": MEMBER}, "status", "Left")
		frappe.set_user(MEMBER)
		self.assertFalse(tc.check_app_permission())


class TestActiveTeam(TeamCockpitTestCase):
	def test_first_team_until_the_user_picks_one(self):
		frappe.set_user(BOTH)
		self.assertEqual(tc.get_teams()["active"], ALPHA)

		self.assertEqual(tc.set_active_team(BETA)["active"], BETA)
		self.assertEqual(tc.get_team_settings(), {"team": BETA, "teams": [ALPHA, BETA]})

	def test_a_team_the_user_is_not_in_cannot_be_picked(self):
		frappe.set_user(MEMBER)
		with self.assertRaises(frappe.PermissionError):
			tc.set_active_team(BETA)
		self.assertEqual(teams.active_team(), ALPHA)

	def test_falls_back_when_the_user_left_the_stored_team(self):
		frappe.set_user(BOTH)
		tc.set_active_team(BETA)

		frappe.set_user("Administrator")
		beta = frappe.get_doc("Team", BETA)
		beta.set("team_members", [])
		beta.save(ignore_permissions=True)

		frappe.set_user(BOTH)
		self.assertEqual(teams.active_team(), ALPHA)


class TestTeamScope(TeamCockpitTestCase):
	def test_issues_and_tasks_of_the_team_only(self):
		mine, theirs, nobodys = self.issue("Alpha issue", ALPHA), self.issue("Beta issue", BETA), self.issue("No team")
		my_task, their_task = self.task("Alpha task", ALPHA), self.task("Beta task", BETA)

		frappe.set_user(MEMBER)
		issues = {row["name"] for row in tc.get_issues()["items"]}
		self.assertIn(mine.name, issues)
		self.assertFalse({theirs.name, nobodys.name} & issues)
		tasks = {row["name"] for row in tc.get_tasks()}
		self.assertIn(my_task.name, tasks)
		self.assertNotIn(their_task.name, tasks)

		self.assertEqual(tc.get_issue(mine.name)["name"], mine.name)
		self.assertEqual(tc.get_task(my_task.name)["name"], my_task.name)
		with self.assertRaises(frappe.ValidationError):
			tc.get_issue(theirs.name)
		with self.assertRaises(frappe.ValidationError):
			tc.get_task(their_task.name)

	def test_switching_the_team_switches_the_lists(self):
		alpha, beta = self.task("Alpha task", ALPHA), self.task("Beta task", BETA)

		frappe.set_user(BOTH)
		self.assertEqual({alpha.name}, {row["name"] for row in tc.get_tasks()} & {alpha.name, beta.name})
		tc.set_active_team(BETA)
		self.assertEqual({beta.name}, {row["name"] for row in tc.get_tasks()} & {alpha.name, beta.name})

	def test_records_of_a_team_project_are_in_scope(self):
		if not frappe.get_meta("Project").has_field("custom_implementation"):
			self.skipTest("Project.custom_implementation is not on this site")
		project = frappe.get_doc({"doctype": "Project", "project_name": "_Test Team Cockpit Project"}).insert(
			ignore_permissions=True
		)
		issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Through the project", "project": project.name}
		).insert(ignore_permissions=True)

		frappe.set_user(MEMBER)
		self.assertNotIn(issue.name, {row["name"] for row in tc.get_issues()["items"]})

		# stands in for Project.custom_implementation -> Implementation.team
		from unittest.mock import patch

		with patch("phamos.cockpits.teams.team_projects", return_value=[project.name]):
			self.assertIn(issue.name, {row["name"] for row in tc.get_issues()["items"]})
			self.assertEqual(tc.get_issue(issue.name)["name"], issue.name)

	def test_created_records_carry_the_team(self):
		frappe.set_user(MEMBER)
		issue = tc.create_issue("Created in the Team Cockpit")
		self.assertEqual(frappe.db.get_value("Issue", issue["name"], "custom_team"), ALPHA)

		task = tc.create_task(
			"Created in the Team Cockpit",
			priority="Medium",
			exp_start_date=today(),
			exp_end_date=add_days(today(), 2),
			expected_time=1,
			custom_task_owner=MEMBER,
		)
		self.assertEqual(frappe.db.get_value("Task", task["name"], "custom_team"), ALPHA)
		self.assertIn(task["name"], {row["name"] for row in tc.get_tasks()})

	def test_a_task_made_from_an_issue_carries_the_team(self):
		issue = self.issue("Becomes a task", ALPHA)

		frappe.set_user(MEMBER)
		result = tc.create_task_from_issue(
			issue.name, exp_start_date=today(), exp_end_date=add_days(today(), 1), assignees=[MEMBER]
		)
		self.assertEqual(frappe.db.get_value("Task", result["task"]["name"], "custom_team"), ALPHA)

	def test_team_mates_are_the_people_to_assign(self):
		frappe.set_user(MEMBER)
		shortlist = {user["name"] for user in tc.get_form_options()["shortlist_users"]}
		self.assertEqual(shortlist, {LEAD, CO_LEAD, MEMBER, BOTH})

	def test_checklists_only_on_the_teams_records(self):
		theirs = self.task("Beta task", BETA)
		frappe.set_user(MEMBER)
		with self.assertRaises(frappe.ValidationError):
			tc.create_checklist("Task", theirs.name)


class TestCockpitSwitcher(TeamCockpitTestCase):
	def test_boot_lists_the_cockpits_the_user_may_open(self):
		frappe.set_user(MEMBER)
		routes = [cockpit["route"] for cockpit in spa_boot.user_cockpits()]
		self.assertIn("/personal-cockpit", routes)
		self.assertIn(ROUTE, routes)
		self.assertNotIn("/general-management-cockpit", routes)

		frappe.set_user(OUTSIDER)
		routes = [cockpit["route"] for cockpit in spa_boot.user_cockpits()]
		self.assertIn("/personal-cockpit", routes)
		self.assertNotIn(ROUTE, routes)

	def test_only_cockpits_are_offered(self):
		frappe.set_user("Administrator")
		routes = {cockpit["route"] for cockpit in spa_boot.user_cockpits()}
		self.assertEqual(routes, set(COCKPITS))
