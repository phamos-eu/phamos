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
		own = {
			"get_teams",
			"set_active_team",
			# statistics and implementations (#1975, #1976)
			"get_hours_statistics",
			"get_team_implementations",
			"get_gitlab_statistics",
			# team mates and team chat (#1978)
			"get_team_mates",
			"get_team_chat",
			"ensure_team_chat",
			# appointments with leave and holidays (#1979)
			"get_team_appointments",
			"get_appointment_options",
			"save_appointment",
			"delete_appointment",
			"get_team_absences",
			# team ideas (#1980)
			"get_team_ideas",
			"get_idea_for_vote",
			"vote_idea",
			"create_team_idea",
			"get_idea_chat",
			"ensure_idea_chat",
			# successes (#1981)
			"get_team_successes",
			"get_success_options",
			"give_kudos",
			"add_customer_praise",
		}
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

	def test_team_opens_the_implementation_specific_section_on_every_issue(self):
		from phamos.phriend import setup as phriend_setup

		phriend_setup.ensure_issue_fields()
		frappe.clear_cache(doctype="Issue")
		meta = frappe.get_meta("Issue")
		section, team, reporter = meta.fields[:3]
		self.assertEqual(section.fieldname, "custom_implementation_specific")
		# shown on every Issue, so a team can be set on each of them
		self.assertFalse(section.depends_on)
		self.assertEqual(team.fieldname, "custom_team")
		# Phriend's fields follow and stay hidden on Issues that are no report and have no GitLab issue
		self.assertEqual(reporter.fieldname, "phriend_reported_by")
		for fieldname in (
			"phriend_reported_by",
			"phriend_reported_by_name",
			"phriend_source_system",
			"custom_implementation",
			"phriend_gitlab_issues",
			"phriend_col",
			"phriend_screenshot_preview",
		):
			self.assertEqual(meta.get_field(fieldname).depends_on, phriend_setup.PHRIEND_OR_GITLAB, fieldname)
		self.assertEqual(meta.get_field("phriend_type").depends_on, phriend_setup.ONLY_PHRIEND)


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

	def test_system_manager_opens_every_team_without_being_a_member(self):
		frappe.set_user(_make_user(MANAGER, ["System Manager"]))
		self.assertEqual(teams.member_teams(), [])
		self.assertTrue({ALPHA, BETA} <= set(teams.available_teams()))
		self.assertEqual(tc.set_active_team(BETA)["active"], BETA)

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

	def test_link_search_for_a_new_checklist_finds_the_teams_records(self):
		# Called the way the "Linked record" field calls it: through the link search, which passes
		# the arguments by position. A decorator in the wrong order breaks exactly this.
		from frappe.desk.search import search_widget

		mine, theirs = self.task("Alpha searchable task", ALPHA), self.task("Beta searchable task", BETA)
		frappe.set_user(MEMBER)
		rows = search_widget(
			"Task", "searchable", query="phamos.api.team_cockpit.checklist_reference_query", page_length=20
		)
		names = {row[0] for row in rows}
		self.assertIn(mine.name, names)
		self.assertNotIn(theirs.name, names)

	def test_another_teams_records_cannot_be_changed(self):
		issue, task, mine = self.issue("Beta issue", BETA), self.task("Beta task", BETA), self.task("Alpha task", ALPHA)
		frappe.set_user(MEMBER)
		for change in (
			lambda: tc.update_issue(issue.name, subject="Taken over"),
			lambda: tc.update_status(issue.name, "Closed"),
			lambda: tc.set_assignees(issue.name, [MEMBER]),
			lambda: tc.update_task(task.name, subject="Taken over"),
			lambda: tc.update_task_status(task.name, "Working"),
			lambda: tc.set_task_assignees(task.name, [MEMBER]),
			lambda: tc.add_task_dependency(mine.name, task.name),
			lambda: tc.create_task_from_issue(
				issue.name, exp_start_date=today(), exp_end_date=add_days(today(), 1), assignees=[MEMBER]
			),
		):
			with self.assertRaises(frappe.ValidationError):
				change()
		self.assertEqual(frappe.db.get_value("Issue", issue.name, ["subject", "status"]), ("Beta issue", "Open"))
		self.assertEqual(frappe.db.get_value("Task", task.name, "subject"), "Beta task")

	def test_the_timesheet_task_list_stays_empty(self):
		# a team has no timesheet project; the endpoint must not list any project's Tasks instead
		project = frappe.get_doc({"doctype": "Project", "project_name": "_Test Team Cockpit Other"}).insert(
			ignore_permissions=True
		)
		frappe.get_doc({"doctype": "Task", "subject": "Not the team's", "project": project.name}).insert(
			ignore_permissions=True
		)
		frappe.set_user(MEMBER)
		self.assertEqual(tc.get_timesheet_project_tasks(project=project.name), [])


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


class TestSetTeamFromOtherCockpits(TeamCockpitTestCase):
	"""Members put records into their own team from the other cockpits (#1955)."""

	def mine(self, doctype, subject, team=None):
		# created by the member, so it is in their Personal Cockpit
		frappe.set_user(MEMBER)
		doc = frappe.get_doc({"doctype": doctype, "subject": subject, "custom_team": team}).insert()
		return doc.name

	def test_member_puts_an_issue_and_a_task_into_their_team_and_out_again(self):
		from phamos.api import personal_cockpit as pc

		issue, task = self.mine("Issue", "Mine to share"), self.mine("Task", "Task to share")
		self.assertEqual(pc.get_form_options()["teams"], [ALPHA])

		self.assertEqual(pc.update_issue(issue, custom_team=ALPHA)["custom_team"], ALPHA)
		self.assertEqual(pc.update_task(task, custom_team=ALPHA)["custom_team"], ALPHA)
		# now it is the team's: it shows in the Team Cockpit
		self.assertIn(issue, {row["name"] for row in tc.get_issues()["items"]})

		self.assertIsNone(pc.update_issue(issue, custom_team="")["custom_team"])
		# the page sends "" for "—"; None means the field was not sent at all
		self.assertIsNone(pc.update_task(task, custom_team="")["custom_team"])

	def test_another_team_is_refused_both_ways(self):
		from phamos.api import personal_cockpit as pc

		issue, theirs = self.mine("Issue", "Not for Beta"), self.mine("Task", "Beta's task", team=BETA)
		with self.assertRaises(frappe.PermissionError):
			pc.update_issue(issue, custom_team=BETA)
		# a record of another team is not taken out of it, nor moved into the own team
		for value in ("", ALPHA):
			with self.assertRaises(frappe.PermissionError):
				pc.update_task(theirs, custom_team=value)
		self.assertEqual(frappe.db.get_value("Task", theirs, "custom_team"), BETA)

	def test_general_management_sets_any_team(self):
		from phamos.api import personal_cockpit as pc

		issue = self.mine("Issue", "For any team")
		frappe.set_user("Administrator")
		frappe.share.add("Issue", issue, MANAGER, write=1)
		frappe.get_doc("Issue", issue).db_set("owner", MANAGER)
		frappe.set_user(MANAGER)
		self.assertIn(BETA, pc.get_form_options()["teams"])
		self.assertEqual(pc.update_issue(issue, custom_team=BETA)["custom_team"], BETA)

	def test_not_changed_inside_the_team_cockpit(self):
		issue = self.mine("Issue", "Stays in Alpha", team=ALPHA)
		self.assertNotIn("teams", tc.get_form_options())
		with self.assertRaises(frappe.ValidationError):
			tc.update_issue(issue, custom_team="")
