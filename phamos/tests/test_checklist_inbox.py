# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the SPA checklist template read scope."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.checklist_inbox import get_checklist_template


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
