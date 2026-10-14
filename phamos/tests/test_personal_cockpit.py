# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Personal Cockpit (#1540): the cockpit engine scoped to the session user, and the
retirement of I Own My Work and the cockpit Raven chat (#1456)."""

from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.desk.form.assign_to import add as add_assignment
from frappe.tests.utils import FrappeTestCase
from frappe.website.path_resolver import resolve_redirect

from phamos.api import department_cockpit as dc
from phamos.api import human_resources_spa
from phamos.api import personal_cockpit as pc

USER_A = "personal-a@example.com"
USER_B = "personal-b@example.com"


def _whitelisted(module):
	return {name for name, fn in vars(module).items() if callable(fn) and fn in frappe.whitelisted}


# Issue needs Support Team (or Ops User), Task needs Projects User, Checklist System Manager.
SYSTEM_USER_ROLES = ("System Manager", "Support Team", "Projects User")


def _ensure_user(email, user_type="System User"):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"user_type": user_type,
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	if user_type == "System User":
		missing = set(SYSTEM_USER_ROLES) - set(frappe.get_roles(email))
		if missing:
			frappe.get_doc("User", email).add_roles(*missing)
	return email


def _assign(doctype, name, user):
	add_assignment({"doctype": doctype, "name": name, "assign_to": [user], "description": name})


class TestPersonalCockpitWiring(FrappeTestCase):
	def test_exposes_the_department_endpoints(self):
		# The shared spa_shared views call these by name; later MRs may add more (ToDos, Today).
		expected = {
			name.replace("get_human_resources_settings", pc.CONFIG.settings_method_name)
			for name in _whitelisted(human_resources_spa)
		}
		self.assertLessEqual(expected, _whitelisted(pc))

	def test_config_is_personal_and_needs_no_settings(self):
		self.assertTrue(pc.CONFIG.is_personal)
		self.assertIsNone(dc._get_department(pc.CONFIG))
		self.assertIsNone(dc._require_department(pc.CONFIG))
		self.assertEqual(human_resources_spa.CONFIG.scope, "department")
		self.assertEqual(pc.get_personal_settings(), {})

	def test_unknown_scope_is_rejected(self):
		with self.assertRaises(ValueError):
			dc.CockpitConfig(label="X", department_field="", project_field="", roles=(), scope="team")

	def test_form_options_have_no_department_default(self):
		options = pc.get_form_options()
		for key in ("priorities", "issue_types", "departments", "projects", "shortlist_users"):
			self.assertIn(key, options)
		for key in ("users", "chat", ""):
			self.assertNotIn(key, options)

	def test_timesheet_tasks_without_project_are_empty(self):
		self.assertEqual(pc.get_timesheet_project_tasks(), [])

	def test_apps_screen_shows_personal_cockpit_only(self):
		apps = {app["name"]: app for app in frappe.get_hooks("add_to_apps_screen", app_name="phamos")}
		self.assertNotIn("i_own_my_work", apps)
		self.assertEqual(apps["personal_cockpit"]["route"], "/personal-cockpit")

	def test_old_routes_redirect_permanently(self):
		cases = {
			"i-own-my-work": "/personal-cockpit",
			"i-own-my-work/issue/ISS-1": "/personal-cockpit/issues/list/ISS-1",
			"i-own-my-work/issues/ISS-1": "/personal-cockpit/issues/list/ISS-1",
			"i-own-my-work/checklists/CHK-1": "/personal-cockpit/checklists/CHK-1",
			"i_own_my_work": "/personal-cockpit",
		}
		for old, new in cases.items():
			with self.subTest(path=old):
				frappe.cache.hdel("website_redirects", old)
				with self.assertRaises(frappe.Redirect) as ctx:
					resolve_redirect(old)
				self.assertEqual(frappe.flags.redirect_location, new)
				self.assertEqual(ctx.exception.http_status_code, 301)

	def test_lookalike_route_is_not_redirected(self):
		frappe.cache.hdel("website_redirects", "i-own-my-work-archive")
		self.assertIsNone(resolve_redirect("i-own-my-work-archive"))

	def test_no_code_refers_to_the_retired_apps(self):
		app_dir = Path(frappe.get_app_path("phamos"))
		needles = ("i_own_my_work", "i-own-my-work", "I Own My Work", "issue_raven")
		allowed = {
			app_dir / "hooks.py",  # redirects from the old routes
			app_dir / "patches" / "v1_0" / "retire_i_own_my_work_default_app.py",
			app_dir / "patches.txt",
		}
		offenders = []
		for path in app_dir.rglob("*"):
			if path.suffix not in (".py", ".json", ".csv", ".txt") or path in allowed:
				continue
			if "tests" in path.parts or "node_modules" in path.parts or "public" in path.parts:
				continue
			text = path.read_text(errors="ignore")
			offenders += [f"{path.relative_to(app_dir)}: {n}" for n in needles if n in text]
		self.assertEqual(offenders, [])


class TestPersonalCockpitPermission(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_system_users_may_open_it(self):
		frappe.set_user(_ensure_user(USER_A))
		self.assertTrue(pc.check_app_permission())

	def test_website_users_and_guests_may_not(self):
		frappe.set_user(_ensure_user("personal-web@example.com", user_type="Website User"))
		self.assertFalse(pc.check_app_permission())
		frappe.set_user("Guest")
		self.assertFalse(pc.check_app_permission())


class TestPersonalScope(FrappeTestCase):
	def setUp(self):
		# Assigning notifies the assignee; in tests that e-mail is sent at once and the
		# e-mail queue commits, which would leave these fixtures behind on the site.
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)

		frappe.set_user("Administrator")
		_ensure_user(USER_A)
		_ensure_user(USER_B)
		self.issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Personal scope issue"}
		).insert(ignore_permissions=True)
		self.task = frappe.get_doc(
			{"doctype": "Task", "subject": "Personal scope task", "status": "Open"}
		).insert(ignore_permissions=True)
		_assign("Issue", self.issue.name, USER_A)
		_assign("Task", self.task.name, USER_A)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_assigned_issue_is_listed_and_readable(self):
		frappe.set_user(USER_A)
		names = [row["name"] for row in pc.get_issues(include_closed=1)["items"]]
		self.assertIn(self.issue.name, names)
		self.assertEqual(pc.get_issue(self.issue.name)["name"], self.issue.name)

	def test_issue_of_someone_else_is_hidden_and_refused(self):
		frappe.set_user(USER_B)
		names = [row["name"] for row in pc.get_issues(include_closed=1)["items"]]
		self.assertNotIn(self.issue.name, names)
		with self.assertRaises(frappe.ValidationError):
			pc.get_issue(self.issue.name)

	def test_assigned_task_is_listed_and_readable(self):
		frappe.set_user(USER_A)
		self.assertIn(self.task.name, [row["name"] for row in pc.get_tasks()])
		self.assertEqual(pc.get_task(self.task.name)["name"], self.task.name)

	def test_task_of_someone_else_is_refused(self):
		frappe.set_user(USER_B)
		self.assertNotIn(self.task.name, [row["name"] for row in pc.get_tasks()])
		with self.assertRaises(frappe.ValidationError):
			pc.get_task(self.task.name)

	def test_my_unassigned_task_is_readable_but_not_listed(self):
		frappe.set_user(USER_B)
		own = frappe.get_doc({"doctype": "Task", "subject": "Own task", "status": "Open"}).insert()
		self.assertEqual(pc.get_task(own.name)["name"], own.name)
		self.assertNotIn(own.name, [row["name"] for row in pc.get_tasks()])

	def test_removing_myself_from_a_task_does_not_fail(self):
		frappe.set_user(USER_A)
		result = pc.set_task_assignees(self.task.name, users=[])
		self.assertEqual(result["assignees"], [])

	def test_new_issue_is_assigned_to_me(self):
		frappe.set_user(USER_A)
		issue = pc.create_issue(subject="Created in the Personal Cockpit")
		self.assertEqual(issue["assignees"], [USER_A])

	def test_new_task_is_assigned_to_me_without_a_department(self):
		frappe.set_user(USER_A)
		task = pc.create_task(subject="Created in the Personal Cockpit")
		self.assertEqual(task["assignees"], [USER_A])
		self.assertFalse(task["department"])

	def test_new_task_takes_the_department_of_its_project(self):
		with patch("frappe.db.get_value", return_value="Human Resources") as get_value:
			self.assertEqual(dc._project_department("PROJ-1"), "Human Resources")
		get_value.assert_called_once_with("Project", "PROJ-1", "department")
		self.assertIsNone(dc._project_department(None))

	def test_checklists_i_own_and_on_my_records_are_listed(self):
		other_issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Somebody else's issue"}
		).insert(ignore_permissions=True)
		_assign("Issue", other_issue.name, USER_B)
		mine_elsewhere = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "Owned by A on B's issue",
				"checklist_owner": USER_A,
				"document": "Issue",
				"reference_record": other_issue.name,
			}
		).insert(ignore_permissions=True)
		on_my_issue = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "On A's issue",
				"checklist_owner": USER_B,
				"document": "Issue",
				"reference_record": self.issue.name,
			}
		).insert(ignore_permissions=True)

		frappe.set_user(USER_A)
		names = {row["name"] for row in pc.get_checklists(include_completed=1)["items"]}
		self.assertIn(mine_elsewhere.name, names)
		self.assertIn(on_my_issue.name, names)

	def test_checklist_on_a_foreign_issue_is_refused(self):
		frappe.set_user(USER_B)
		with self.assertRaises(frappe.ValidationError):
			pc.create_checklist("Issue", self.issue.name, name="Not mine", checklist_owner=USER_B)

	def test_reference_query_offers_my_issues(self):
		frappe.set_user(USER_A)
		rows = dc.checklist_reference_query(pc.CONFIG, "Issue", self.issue.name, "name", 0, 20, {})
		self.assertIn(self.issue.name, [row[0] for row in rows])
