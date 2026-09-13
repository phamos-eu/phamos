# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestChecklist(FrappeTestCase):
	def test_completed_on_tracks_completed_status(self):
		checklist = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "Completion timestamp test",
				"checklist_owner": "Administrator",
				"checklist_items": [{"description": "Test item", "done": 1}],
			}
		).insert()
		self.addCleanup(frappe.delete_doc, "Checklist", checklist.name, force=True)

		self.assertEqual(checklist.status, "Completed")
		self.assertIsNotNone(checklist.completed_on)

		checklist.checklist_items[0].done = 0
		checklist.save()
		self.assertEqual(checklist.status, "Not Started")
		self.assertIsNone(checklist.completed_on)
