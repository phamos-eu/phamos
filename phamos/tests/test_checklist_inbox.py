# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the checklist inbox endpoints (on version-15: loading several checklists at
once, #1796; reordering items, #1919)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.checklist_inbox import get_checklists, move_spa_checklist_item


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


class TestMoveSpaChecklistItem(FrappeTestCase):
	"""Reorder within a checklist (#1919)."""

	def _doc(self, names):
		doc = MagicMock()
		doc.checklist_items = [SimpleNamespace(name=n, idx=i + 1) for i, n in enumerate(names)]
		return doc

	def _move(self, doc, item, to_index):
		with (
			patch("phamos.api.checklist_inbox._require_checklist_write", return_value=doc),
			patch("phamos.api.checklist_inbox.get_checklist", return_value={"name": "CHK-1"}),
		):
			return move_spa_checklist_item("CHK-1", item, to_index)

	def test_moves_and_renumbers(self):
		doc = self._doc(["A", "B", "C", "D"])
		self.assertEqual(self._move(doc, "D", "1"), {"name": "CHK-1"})
		self.assertEqual([r.name for r in doc.checklist_items], ["A", "D", "B", "C"])
		self.assertEqual([r.idx for r in doc.checklist_items], [1, 2, 3, 4])
		doc.save.assert_called_once()

	def test_to_the_end_and_to_the_start(self):
		doc = self._doc(["A", "B", "C"])
		self._move(doc, "A", 2)
		self.assertEqual([r.name for r in doc.checklist_items], ["B", "C", "A"])
		self._move(doc, "A", 0)
		self.assertEqual([r.name for r in doc.checklist_items], ["A", "B", "C"])

	def test_refuses_bad_positions_and_unknown_items(self):
		for item, to_index in (("A", 3), ("A", -1), ("A", "x"), ("NOPE", 0), ("", 0)):
			doc = self._doc(["A", "B", "C"])
			with self.assertRaises(frappe.ValidationError):
				self._move(doc, item, to_index)
			doc.save.assert_not_called()

	def test_needs_write_permission(self):
		with patch(
			"phamos.api.checklist_inbox._require_checklist_write", side_effect=frappe.PermissionError
		):
			with self.assertRaises(frappe.PermissionError):
				move_spa_checklist_item("CHK-1", "A", 0)
