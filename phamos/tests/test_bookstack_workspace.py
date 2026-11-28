# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Bookstack workspace and Apps-screen tile (phamos/phamos#2028). Run with
    bench --site <site> run-tests --module phamos.tests.test_bookstack_workspace
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.bookstack_integration.api import check_app_permission


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc({
			"doctype": "User", "email": email, "first_name": "Bookstack Test", "send_welcome_email": 0,
			"roles": [{"role": r} for r in roles],
		}).insert(ignore_permissions=True)
	return email


class TestBookstackWorkspace(FrappeTestCase):
	def setUp(self):
		frappe.db.savepoint("bookstack_workspace")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="bookstack_workspace")

	def test_tile_only_for_bookstack_roles(self):
		for email, roles, expected in (
			("bs-ws-user@example.com", ["Bookstack User"], True),
			("bs-ws-manager@example.com", ["Bookstack Manager"], True),
			("bs-ws-other@example.com", ["Blogger"], False),
		):
			frappe.set_user(_user(email, roles))
			try:
				self.assertEqual(check_app_permission(), expected, roles)
			finally:
				frappe.set_user("Administrator")

	def test_tile_is_on_the_apps_screen_but_no_cockpit(self):
		# version-15 has no cockpit switcher (spa_boot.user_cockpits) yet; "Open in Cockpit" is checked.
		from phamos.api.issue_cockpits import _cockpit_modules

		tiles = {t["name"]: t for t in frappe.get_hooks("add_to_apps_screen", app_name="phamos")}
		self.assertEqual(tiles["bookstack"]["route"], "/app/bookstack")
		self.assertNotIn("/app/bookstack", [route for _, route in _cockpit_modules()])

	def test_workspace_links_resolve(self):
		ws = frappe.get_doc("Workspace", "Bookstack")

		self.assertEqual(ws.module, "Bookstack Integration")
		self.assertEqual({r.role for r in ws.roles}, {"Bookstack User", "Bookstack Manager", "System Manager"})
		for link in ws.links:
			if link.type == "Link":
				self.assertTrue(frappe.db.exists("DocType", link.link_to), link.link_to)
		for shortcut in ws.shortcuts:
			self.assertTrue(frappe.db.exists(shortcut.type, shortcut.link_to), shortcut.link_to)

	def test_manager_can_open_the_browser_page(self):
		roles = {r.role for r in frappe.get_doc("Page", "bookstack-browser").roles}
		self.assertIn("Bookstack Manager", roles)
