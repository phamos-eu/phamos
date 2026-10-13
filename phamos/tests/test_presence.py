# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Soft field locks and presence cards used by the cockpit editors (GitLab #1426)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import presence
from phamos.api.presence import (
	FieldLockedError,
	acquire_field_lock,
	assert_fields_unlocked,
	get_field_locks,
	get_user_cards,
	release_field_lock,
)

OTHER_USER = "presence-other@example.com"


def _make_issue(subject="Presence test issue"):
	return frappe.get_doc({"doctype": "Issue", "subject": subject}).insert(ignore_permissions=True)


class TestFieldLocks(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.issue = _make_issue()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.cache().delete_value(presence._lock_key("Issue", self.issue.name))
		frappe.db.rollback()

	def test_acquire_publishes_and_lists_the_lock(self):
		with patch("phamos.api.presence.frappe.publish_realtime") as publish:
			result = acquire_field_lock("Issue", self.issue.name, "description")
		self.assertTrue(result["ok"])
		self.assertEqual(result["lock"]["user"], "Administrator")
		self.assertEqual(publish.call_args.kwargs["docname"], self.issue.name)
		locks = get_field_locks("Issue", self.issue.name)
		self.assertEqual([lock["fieldname"] for lock in locks], ["description"])

	def test_lock_blocks_other_users_and_not_the_holder(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		assert_fields_unlocked("Issue", self.issue.name, ["description"])  # holder

		frappe.set_user(OTHER_USER)
		with self.assertRaises(FieldLockedError):
			assert_fields_unlocked("Issue", self.issue.name, ["subject", "description"])
		assert_fields_unlocked("Issue", self.issue.name, ["priority"])

	def test_second_user_cannot_take_a_live_lock(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		frappe.set_user(OTHER_USER)
		with patch("phamos.api.presence._validate_target"):
			result = acquire_field_lock("Issue", self.issue.name, "description")
		self.assertFalse(result["ok"])
		self.assertEqual(result["lock"]["user"], "Administrator")

	def test_expired_lock_is_ignored(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		with patch("phamos.api.presence.time.time", return_value=10**12):
			frappe.set_user(OTHER_USER)
			assert_fields_unlocked("Issue", self.issue.name, ["description"])

	def test_release_only_by_holder(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		frappe.set_user(OTHER_USER)
		with patch("phamos.api.presence._validate_target"):
			self.assertFalse(release_field_lock("Issue", self.issue.name, "description")["ok"])
		frappe.set_user("Administrator")
		self.assertTrue(release_field_lock("Issue", self.issue.name, "description")["ok"])
		self.assertEqual(get_field_locks("Issue", self.issue.name), [])

	def test_rejects_unknown_doctypes_and_bad_field_names(self):
		with self.assertRaises(frappe.ValidationError):
			acquire_field_lock("User", "Administrator", "full_name")
		with self.assertRaises(frappe.ValidationError):
			acquire_field_lock("Issue", self.issue.name, "Description; DROP")

	def test_child_row_field_names_are_allowed(self):
		self.assertTrue(acquire_field_lock("Issue", self.issue.name, "note:row-1")["ok"])


class TestUserCards(FrappeTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")

	def test_guest_is_rejected(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_user_cards(["Administrator"])

	def test_portal_users_are_rejected(self):
		frappe.set_user("presence-portal@example.com")
		with patch("phamos.api.presence.frappe.get_cached_value", return_value="Website User"):
			with self.assertRaises(frappe.PermissionError):
				get_user_cards(["Administrator"])

	def test_returns_only_public_fields_in_order(self):
		frappe.set_user("Administrator")
		cards = get_user_cards('["Administrator", "no-such-user@example.com"]')
		self.assertEqual([c["name"] for c in cards], ["Administrator"])
		self.assertEqual(set(cards[0]), {"name", "full_name", "user_image"})
