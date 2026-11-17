# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The General Management Cockpit (#1946): wired like the department cockpits, but only the role
`phamos General Management` (and System Manager) gets in, and that role alone is enough."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from phamos.api import general_management_spa as gm
from phamos.api import software_development_spa
from phamos.api.issue_chat import COCKPIT_PATHS, PERSONAL_COCKPIT_PATH, record_cockpit_path
from phamos.cockpits.settings import COCKPITS, COCKPIT_SETTINGS
from phamos.setup import general_management as setup
from phamos.www import general_management_spa as page

ROUTE = "/general-management-cockpit"
MANAGER = "gm-cockpit-manager@example.com"
PROJECTS_USER = "gm-cockpit-projects-user@example.com"


def _whitelisted(module):
	return {name: fn for name, fn in vars(module).items() if callable(fn) and fn in frappe.whitelisted}


def _make_user(email, roles):
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


def _custom_perm(doctype):
	return frappe.db.get_value(
		"Custom DocPerm",
		{"parent": doctype, "role": setup.GENERAL_MANAGEMENT_ROLE, "permlevel": 0, "if_owner": 0},
		["name", "modified", *setup.GRANTED, *setup.WITHHELD],
		as_dict=True,
	)


class TestGeneralManagementWiring(FrappeTestCase):
	def test_config_fields_exist_in_cockpit_settings(self):
		meta = frappe.get_meta(COCKPIT_SETTINGS)
		for field in (gm.CONFIG.department_field, gm.CONFIG.project_field, "general_management_color"):
			self.assertTrue(meta.has_field(field), field)

	def test_settings_keys_match_frontend_config(self):
		# general_management_frontend/src/config.js reads these keys from get_general_management_settings.
		self.assertEqual(gm.CONFIG.project_name_key, "general_management_timesheet_project_name")

	def test_exposes_the_same_endpoints_as_software_development(self):
		# The shared spa_shared views call these by name, so a missing one breaks a screen.
		# Software Development is the template (#1462); Human Resources has HR-only extras.
		expected = {
			name.replace("get_software_development_settings", gm.CONFIG.settings_method_name)
			for name in _whitelisted(software_development_spa)
		}
		self.assertEqual(set(_whitelisted(gm)), expected)

	def test_every_endpoint_checks_the_role(self):
		ungated = [
			name
			for name, fn in _whitelisted(gm).items()
			if not getattr(fn, "requires_general_management", False)
		]
		self.assertEqual(ungated, [])

	def test_window_colour_and_raven_links(self):
		self.assertEqual(COCKPITS[ROUTE], ("general_management", "#a16207"))
		self.assertIn(("general_management_department", ROUTE), COCKPIT_PATHS)


class TestGeneralManagementAccess(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		setup.after_migrate()
		# A department no other cockpit uses, so Raven links can only point here.
		taken = {
			frappe.db.get_single_value(COCKPIT_SETTINGS, f"{prefix}_department")
			for prefix, _color in COCKPITS.values()
			if prefix not in ("general_management", "personal")
		}
		departments = [
			name
			for name in frappe.get_all("Department", filters={"is_group": 0}, pluck="name")
			if name not in taken
		]
		if not departments:
			self.skipTest("needs a Department no other cockpit uses")
		self.department = departments[0]
		frappe.db.set_single_value(COCKPIT_SETTINGS, gm.CONFIG.department_field, self.department)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_reading_issues_and_tasks_is_not_enough(self):
		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		self.assertTrue(frappe.has_permission("Task", "read"))

		self.assertFalse(gm.check_app_permission())
		with self.assertRaises(frappe.PermissionError):
			gm.get_general_management_settings()
		with self.assertRaises(frappe.PermissionError):
			gm.get_tasks()
		with self.assertRaises(frappe.PermissionError):
			page.get_context(frappe._dict())

	def test_raven_links_open_here_only_for_the_role(self):
		frappe.set_user("Administrator")
		task = frappe.get_doc(
			{"doctype": "Task", "subject": "Company target", "department": self.department}
		).insert()

		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		self.assertEqual(record_cockpit_path("Task", task.name), ROUTE)

		frappe.set_user(_make_user(PROJECTS_USER, ["Projects User"]))
		self.assertEqual(record_cockpit_path("Task", task.name), PERSONAL_COCKPIT_PATH)

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		self.assertFalse(gm.check_app_permission())

	def test_the_role_alone_is_enough(self):
		frappe.set_user(_make_user(MANAGER, [setup.GENERAL_MANAGEMENT_ROLE]))
		self.assertTrue(gm.check_app_permission())

		settings = gm.get_general_management_settings()
		self.assertEqual(settings["general_management_department"], self.department)

		task = gm.create_task(
			"Company target",
			priority="Medium",
			exp_start_date=today(),
			exp_end_date=add_days(today(), 30),
			expected_time=4,
			custom_task_owner=MANAGER,
		)
		self.assertEqual(task["department"], self.department)
		self.assertIn(task["name"], [t["name"] for t in gm.get_tasks()])


class TestGeneralManagementRole(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_role_gets_rights_without_delete(self):
		setup.after_migrate()
		self.assertTrue(frappe.db.exists("Role", setup.GENERAL_MANAGEMENT_ROLE))
		for doctype in setup.DOCTYPES:
			perm = _custom_perm(doctype)
			self.assertIsNotNone(perm, doctype)
			for ptype in setup.GRANTED:
				self.assertEqual(perm[ptype], 1, f"{doctype} {ptype}")
			self.assertEqual(perm["delete"], 0, doctype)

	def test_running_twice_changes_nothing(self):
		setup.after_migrate()
		before = {doctype: _custom_perm(doctype) for doctype in setup.DOCTYPES}
		setup.after_migrate()
		self.assertEqual({doctype: _custom_perm(doctype) for doctype in setup.DOCTYPES}, before)
