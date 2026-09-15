# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for checklist inbox owner search and item deletion."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.checklist_inbox import checklist_owner_query, delete_spa_checklist_item


class TestChecklistOwnerQuery(FrappeTestCase):
	def test_filters_to_enabled_employee_role_users(self):
		with (
			patch("frappe.db.exists", return_value=True),
			patch(
				"frappe.utils.user.get_users_with_role",
				return_value=["a@example.com", "b@example.com", "Guest"],
			),
			patch("frappe.get_list", return_value=[("a@example.com", "A")]) as get_list,
		):
			result = checklist_owner_query("User", "a", "name", 0, 20, "{}")

		self.assertEqual(result, [("a@example.com", "A")])
		args, kwargs = get_list.call_args
		self.assertEqual(args[0], "User")
		in_op, names = kwargs["filters"]["name"]
		self.assertEqual(in_op, "in")
		self.assertEqual(sorted(names), ["a@example.com", "b@example.com"])
		self.assertEqual(kwargs["filters"]["enabled"], 1)
		self.assertEqual(kwargs["filters"]["user_type"], ("!=", "Website User"))

	def test_returns_empty_when_no_employee_role_users(self):
		with (
			patch("frappe.db.exists", return_value=True),
			patch("frappe.utils.user.get_users_with_role", return_value=[]),
			patch("frappe.get_list") as get_list,
		):
			result = checklist_owner_query("User", "", "name", 0, 20, "{}")

		self.assertEqual(result, [])
		get_list.assert_not_called()


class TestDeleteSpaChecklistItem(FrappeTestCase):
	def _checklist_doc(self, item_names):
		doc = MagicMock()
		doc.checklist_items = [SimpleNamespace(name=n) for n in item_names]
		return doc

	def test_removes_matching_item_and_saves(self):
		doc = self._checklist_doc(["ITEM-1", "ITEM-2"])
		with (
			patch(
				"phamos.api.checklist_inbox._require_checklist_write", return_value=doc
			),
			patch(
				"phamos.api.checklist_inbox.get_checklist", return_value={"name": "CHK-1"}
			) as get_checklist,
		):
			result = delete_spa_checklist_item("CHK-1", "ITEM-1")

		removed_row = doc.remove.call_args[0][0]
		self.assertEqual(removed_row.name, "ITEM-1")
		doc.save.assert_called_once()
		get_checklist.assert_called_once_with("CHK-1")
		self.assertEqual(result, {"name": "CHK-1"})

	def test_rejects_missing_item_name(self):
		doc = self._checklist_doc(["ITEM-1"])
		with patch("phamos.api.checklist_inbox._require_checklist_write", return_value=doc):
			with self.assertRaises(frappe.ValidationError):
				delete_spa_checklist_item("CHK-1", "  ")
		doc.remove.assert_not_called()
		doc.save.assert_not_called()

	def test_rejects_unknown_item(self):
		doc = self._checklist_doc(["ITEM-1"])
		with patch("phamos.api.checklist_inbox._require_checklist_write", return_value=doc):
			with self.assertRaises(frappe.ValidationError):
				delete_spa_checklist_item("CHK-1", "ITEM-404")
		doc.remove.assert_not_called()
		doc.save.assert_not_called()
