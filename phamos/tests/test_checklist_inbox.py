# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for checklist inbox: template read scope, owner search, item
deletion, and inbox row cap / truncation reporting."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.checklist_inbox import (
	CHECKLIST_INBOX_LIMIT,
	checklist_owner_query,
	delete_spa_checklist_item,
	_readable_checklist_rows,
	get_checklist_inbox,
	get_checklist_template,
)


class TestGetChecklistTemplate(FrappeTestCase):
	def test_rejects_unsupported_document(self):
		with patch("frappe.has_permission"):
			with self.assertRaises(frappe.ValidationError):
				get_checklist_template("Not A Doctype", "CHKT-0001")

	def test_scopes_lookup_to_the_given_document(self):
		"""A template fetched for one Document context must not leak content
		scoped to another — the lookup filters on `document` server-side
		rather than trusting the client to check it after the fact."""
		with (
			patch("frappe.has_permission"),
			patch("frappe.db.get_value", return_value=None) as get_value,
		):
			with self.assertRaises(frappe.ValidationError):
				get_checklist_template("Task", "CHKT-0001")

			args, _ = get_value.call_args
			self.assertEqual(args[0], "Checklist Template")
			filters = args[1]
			self.assertEqual(filters["name"], "CHKT-0001")
			self.assertEqual(filters["document"], "Task")
			self.assertEqual(filters["docstatus"], 1)

	def test_returns_payload_for_matching_document(self):
		template_row = frappe._dict(
			name="CHKT-0001",
			title="Onboarding",
			document="Task",
			checklist_template_owner="admin@example.com",
		)
		with (
			patch("frappe.has_permission"),
			patch("frappe.db.get_value", return_value=template_row),
			patch("frappe.get_all", return_value=[]),
		):
			result = get_checklist_template("Task", "CHKT-0001")
			self.assertEqual(result["name"], "CHKT-0001")
			self.assertEqual(result["document"], "Task")
			self.assertEqual(result["items"], [])


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


def _row(name):
	return frappe._dict(
		name=name,
		status="Open",
		completion_percentage=0,
		document="Issue",
		reference_record="ISS-1",
		modified="2026-01-01 10:00:00",
		owner="user@example.com",
	)


class TestGetChecklistInbox(FrappeTestCase):
	def test_not_truncated_under_the_cap(self):
		rows = [_row(f"CHK-{i}") for i in range(3)]
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.checklist_inbox._checklist_has_title_field", return_value=False
			),
			patch("frappe.get_list", return_value=rows),
			patch(
				"phamos.api.checklist_inbox._readable_checklist_rows",
				side_effect=lambda given: given,
			),
			patch("phamos.api.checklist_inbox._item_counts_map", return_value={}),
		):
			result = get_checklist_inbox()

		self.assertFalse(result["truncated"])
		self.assertEqual(len(result["items"]), 3)

	def test_truncated_when_over_the_cap(self):
		rows = [_row(f"CHK-{i}") for i in range(CHECKLIST_INBOX_LIMIT + 1)]
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.checklist_inbox._checklist_has_title_field", return_value=False
			),
			patch("frappe.get_list", return_value=rows),
			patch(
				"phamos.api.checklist_inbox._readable_checklist_rows",
				side_effect=lambda given: given,
			),
			patch("phamos.api.checklist_inbox._item_counts_map", return_value={}),
		):
			result = get_checklist_inbox()

		self.assertTrue(result["truncated"])
		self.assertEqual(len(result["items"]), CHECKLIST_INBOX_LIMIT)


class TestReadableChecklistRows(FrappeTestCase):
	"""Checklist permissions are role-based and span every department's
	doctypes, so the inbox has to defer to the record each one hangs off."""

	def test_drops_rows_whose_parent_is_not_readable(self):
		rows = [
			{"name": "CHK-1", "document": "Issue", "reference_record": "ISS-mine"},
			{"name": "CHK-2", "document": "Issue", "reference_record": "ISS-theirs"},
		]
		with (
			patch("frappe.has_permission", return_value=True),
			patch("frappe.get_list", return_value=["ISS-mine"]),
		):
			kept = _readable_checklist_rows(rows)

		self.assertEqual([row["name"] for row in kept], ["CHK-1"])

	def test_drops_everything_when_the_parent_doctype_is_off_limits(self):
		rows = [{"name": "CHK-1", "document": "Task", "reference_record": "TASK-1"}]
		with patch("frappe.has_permission", return_value=False):
			self.assertEqual(_readable_checklist_rows(rows), [])

	def test_keeps_rows_with_no_parent(self):
		"""A checklist that references nothing has no parent to defer to."""
		rows = [{"name": "CHK-1", "document": None, "reference_record": None}]
		with patch("frappe.has_permission", return_value=True):
			self.assertEqual(_readable_checklist_rows(rows), rows)

	def test_asks_once_per_parent_doctype(self):
		rows = [
			{"name": "CHK-1", "document": "Issue", "reference_record": "ISS-1"},
			{"name": "CHK-2", "document": "Issue", "reference_record": "ISS-2"},
			{"name": "CHK-3", "document": "Task", "reference_record": "TASK-1"},
		]
		with (
			patch("frappe.has_permission", return_value=True),
			patch("frappe.get_list", return_value=[]) as get_list,
		):
			_readable_checklist_rows(rows)

		self.assertEqual(get_list.call_count, 2)
