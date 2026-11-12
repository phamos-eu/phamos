# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""`personal_cockpit.update_task`: Task autosave in the Personal Cockpit (#1766).

Mirrors the Issue tests: the Task is created by Administrator, so the personal scope
admits it through the owner fallback.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.personal_cockpit import get_task, update_task


class TestUpdateTask(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.task = frappe.get_doc(
			{"doctype": "Task", "subject": "Autosave task test", "description": "<p>one</p>"}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_partial_update_leaves_other_fields_alone(self):
		result = update_task(self.task.name, description="<p>two</p>")
		self.assertIn("two", result["description"])
		self.assertEqual(result["subject"], "Autosave task test")

	def test_empty_subject_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			update_task(self.task.name, subject="   ")

	def test_stale_modified_raises_timestamp_mismatch(self):
		stale = str(self.task.modified)
		update_task(self.task.name, description="<p>first</p>", modified=stale)
		with self.assertRaises(frappe.TimestampMismatchError):
			update_task(self.task.name, description="<p>second</p>", modified=stale)

	def test_current_modified_is_accepted(self):
		current = str(get_task(self.task.name)["modified"])
		result = update_task(self.task.name, subject="Renamed", modified=current)
		self.assertEqual(result["subject"], "Renamed")
