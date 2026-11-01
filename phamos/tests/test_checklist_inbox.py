# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the checklist inbox endpoints (on version-15: loading several checklists at
once, #1796)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.checklist_inbox import get_checklists


class TestGetChecklists(FrappeTestCase):
	"""Several checklists in one call for a record's checklist section (#1796)."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.names = [
			frappe.get_doc(
				{
					"doctype": "Checklist",
					"title": f"Batch test {i}",
					"checklist_owner": "Administrator",
					"checklist_items": [{"description": "one"}, {"description": "two", "done": 1}],
				}
			)
			.insert()
			.name
			for i in range(3)
		]

	def tearDown(self):
		frappe.db.rollback()

	def test_returns_each_readable_checklist_with_its_items(self):
		hidden = self.names[2]
		real_require = frappe.get_attr("phamos.api.checklist_inbox._require_checklist_read")

		def require(name):
			if name == hidden:
				raise frappe.PermissionError
			return real_require(name)

		with patch("phamos.api.checklist_inbox._require_checklist_read", side_effect=require):
			result = get_checklists(frappe.as_json([*self.names, "CHK-DOES-NOT-EXIST"]))
		self.assertEqual(sorted(result), sorted(self.names[:2]))
		first = result[self.names[0]]
		self.assertEqual([i["description"] for i in first["items"]], ["one", "two"])
		self.assertEqual((first["done_count"], first["total_count"]), (1, 2))

	def test_refuses_more_than_a_section_shows(self):
		from phamos.api.checklist_inbox import MAX_CHECKLISTS_PER_CALL

		with self.assertRaises(frappe.ValidationError):
			get_checklists([f"CHK-{i}" for i in range(MAX_CHECKLISTS_PER_CALL + 1)])
