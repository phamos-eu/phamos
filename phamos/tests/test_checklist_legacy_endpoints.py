# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The legacy Checklist helpers are gone (#1591).

get_linked_checklists listed the Checklists of any record without a permission
check. The Desk pop-up uses checklist_inbox.get_checklists_for_reference since
#1005, which must refuse a user without Checklist read.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import checklist_inbox
from phamos.phamos.doctype.checklist import checklist as checklist_module

USER_NO_CHECKLIST = "chk-legacy@example.com"


class TestChecklistLegacyEndpoints(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		if not frappe.db.exists("User", USER_NO_CHECKLIST):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": USER_NO_CHECKLIST,
					"first_name": "chk-legacy",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		frappe.get_doc("User", USER_NO_CHECKLIST).add_roles("Projects User")
		self.task = frappe.get_doc({"doctype": "Task", "subject": "Checklist legacy test"}).insert(
			ignore_permissions=True
		)
		self.checklist = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "Legacy test",
				"checklist_owner": "Administrator",
				"document": "Task",
				"reference_record": self.task.name,
				"checklist_items": [{"description": "Item"}],
			}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_legacy_endpoints_are_removed(self):
		for name in ("get_linked_checklists", "get_checklist_details"):
			self.assertFalse(hasattr(checklist_module, name), name)
			with self.assertRaises(Exception):
				frappe.get_attr(f"phamos.phamos.doctype.checklist.checklist.{name}")

	def test_reader_sees_linked_checklists(self):
		rows = checklist_inbox.get_checklists_for_reference("Task", self.task.name)
		self.assertIn(self.checklist.name, [r["name"] for r in rows])

	def test_user_without_checklist_read_is_refused(self):
		frappe.set_user(USER_NO_CHECKLIST)
		self.assertFalse(frappe.has_permission("Checklist", "read"))
		self.assertTrue(frappe.has_permission("Task", "read", doc=self.task.name))
		with self.assertRaises(frappe.PermissionError):
			checklist_inbox.get_checklists_for_reference("Task", self.task.name)
