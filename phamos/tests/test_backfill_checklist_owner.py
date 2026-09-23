# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the checklist_owner backfill patch."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0.backfill_checklist_owner import execute


class TestBackfillChecklistOwner(FrappeTestCase):
	def setUp(self):
		self.enabled_user = self._ensure_user("backfill_enabled@example.com", enabled=1)
		self.disabled_user = self._ensure_user("backfill_disabled@example.com", enabled=0)

	def _ensure_user(self, email, enabled):
		if not frappe.db.exists("User", email):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": email,
					"first_name": email.split("@")[0],
					"enabled": enabled,
				}
			).insert(ignore_permissions=True)
		else:
			frappe.db.set_value("User", email, "enabled", enabled, update_modified=False)
		return email

	def _make_checklist(self, owner, checklist_owner):
		"""Create a Checklist, then force owner/checklist_owner past validate()."""
		doc = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "Backfill patch test",
				"checklist_owner": "Administrator",
			}
		).insert(ignore_permissions=True)
		# validate() requires checklist_owner, so the empty state only exists in the
		# DB -- which is exactly the pre-patch state this backfill has to repair.
		frappe.db.sql(
			"update `tabChecklist` set owner=%s, checklist_owner=%s where name=%s",
			(owner, checklist_owner, doc.name),
		)
		return doc.name

	def test_null_owner_is_filled_from_creator(self):
		name = self._make_checklist(self.enabled_user, None)
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), self.enabled_user
		)

	def test_empty_string_owner_is_filled_from_creator(self):
		name = self._make_checklist(self.enabled_user, "")
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), self.enabled_user
		)

	def test_disabled_creator_falls_back_to_administrator(self):
		name = self._make_checklist(self.disabled_user, None)
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), "Administrator"
		)

	def test_deleted_creator_falls_back_to_administrator(self):
		name = self._make_checklist("gone@example.com", None)
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), "Administrator"
		)

	def test_existing_owner_is_left_alone(self):
		name = self._make_checklist(self.enabled_user, "Administrator")
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), "Administrator"
		)

	def test_is_idempotent(self):
		name = self._make_checklist(self.enabled_user, None)
		execute()
		execute()
		self.assertEqual(
			frappe.db.get_value("Checklist", name, "checklist_owner"), self.enabled_user
		)

	def test_backfilled_record_saves_without_throwing(self):
		name = self._make_checklist(self.enabled_user, None)
		execute()
		doc = frappe.get_doc("Checklist", name)
		doc.save(ignore_permissions=True)
