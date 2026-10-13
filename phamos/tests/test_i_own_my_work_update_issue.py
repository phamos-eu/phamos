# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""`i_own_my_work.update_issue`: the autosave endpoint of the I Own My Work inbox (GitLab #1426)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import presence
from phamos.api.i_own_my_work import get_issue, update_issue
from phamos.api.presence import FieldLockedError, acquire_field_lock


class TestUpdateIssue(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Autosave test", "description": "<p>one</p>"}
		).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache().delete_value(presence._lock_key("Issue", self.issue.name))
		frappe.db.rollback()

	def test_partial_update_leaves_other_fields_alone(self):
		result = update_issue(self.issue.name, description="<p>two</p>")
		self.assertIn("two", result["description"])
		self.assertEqual(result["subject"], "Autosave test")
		self.assertEqual(result["modified_by"], "Administrator")
		self.assertTrue(result["modified_by_name"])

	def test_empty_subject_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			update_issue(self.issue.name, subject="   ")

	def test_stale_modified_raises_timestamp_mismatch(self):
		stale = str(self.issue.modified)
		update_issue(self.issue.name, description="<p>first</p>", modified=stale)
		with self.assertRaises(frappe.TimestampMismatchError):
			update_issue(self.issue.name, description="<p>second</p>", modified=stale)

	def test_current_modified_is_accepted(self):
		current = str(get_issue(self.issue.name)["modified"])
		result = update_issue(self.issue.name, subject="Renamed", modified=current)
		self.assertEqual(result["subject"], "Renamed")

	def test_field_locked_by_someone_else_is_refused(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		frappe.set_user("autosave-other@example.com")
		with (
			patch("frappe.has_permission", return_value=True),
			patch("frappe.model.document.Document.check_permission"),
		):
			with self.assertRaises(FieldLockedError):
				update_issue(self.issue.name, description="<p>theirs</p>")
