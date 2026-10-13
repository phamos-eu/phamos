# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Soft field locks and presence cards used by the cockpit editors (GitLab #1426)."""

import time
from unittest.mock import MagicMock, patch

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
		presence.clear_field_locks("Issue", self.issue.name)
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
		# Let Redis expire the key instead of waiting LOCK_TTL seconds.
		cache = frappe.cache()
		cache.execute_command("PEXPIRE", presence._field_key("Issue", self.issue.name, "description"), 1)
		time.sleep(0.05)
		frappe.set_user(OTHER_USER)
		assert_fields_unlocked("Issue", self.issue.name, ["description"])
		frappe.set_user("Administrator")
		self.assertEqual(get_field_locks("Issue", self.issue.name), [])

	def test_holder_can_refresh_and_expiry_is_reported(self):
		acquire_field_lock("Issue", self.issue.name, "description")
		result = acquire_field_lock("Issue", self.issue.name, "description")
		self.assertTrue(result["ok"])
		self.assertGreater(result["lock"]["expires_in"], 0)
		self.assertLessEqual(result["lock"]["expires_in"], presence.LOCK_TTL)

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


class TestLockEnforcementInCockpitEndpoints(FrappeTestCase):
	"""The cockpit save endpoints refuse fields another user holds a lock on."""

	def setUp(self):
		from phamos.api.department_cockpit import CockpitConfig

		frappe.set_user("Administrator")
		self.hr = CockpitConfig(
			label="HR",
			department_field="human_resources_department",
			project_field="human_resources_timesheet_project",
			roles=("HR Manager", "HR User"),
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		for doctype, name in (("Issue", "ISS-LOCK-1"), ("Task", "TASK-LOCK-1"), ("Checklist", "CHK-LOCK-1")):
			presence.clear_field_locks(doctype, name)

	def _lock_as_admin(self, doctype, name, fieldname):
		with patch("phamos.api.presence._validate_target"):
			self.assertTrue(acquire_field_lock(doctype, name, fieldname)["ok"])
		frappe.set_user(OTHER_USER)

	def _doc(self, name):
		doc = MagicMock()
		doc.name = name
		return doc

	def test_department_update_issue(self):
		from phamos.api.department_cockpit import update_issue

		self._lock_as_admin("Issue", "ISS-LOCK-1", "description")
		doc = self._doc("ISS-LOCK-1")
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit.get_issue", return_value={"name": "ISS-LOCK-1"}),
			patch("frappe.get_doc", return_value=doc),
		):
			with self.assertRaises(FieldLockedError):
				update_issue(self.hr, "ISS-LOCK-1", description="<p>theirs</p>")
			doc.save.assert_not_called()
			update_issue(self.hr, "ISS-LOCK-1", priority="High")
			doc.save.assert_called_once()

	def test_department_update_task(self):
		from phamos.api.department_cockpit import update_task

		self._lock_as_admin("Task", "TASK-LOCK-1", "subject")
		doc = self._doc("TASK-LOCK-1")
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit.get_task", return_value={"name": "TASK-LOCK-1"}),
			patch("frappe.get_doc", return_value=doc),
		):
			with self.assertRaises(FieldLockedError):
				update_task(self.hr, "TASK-LOCK-1", subject="Renamed")
			doc.save.assert_not_called()

	def test_checklist_item_note_is_locked_per_row(self):
		from phamos.api.checklist_inbox import update_spa_checklist_item

		self._lock_as_admin("Checklist", "CHK-LOCK-1", "note:row-1")
		with (
			patch("phamos.api.checklist_inbox._require_checklist_write"),
			patch("phamos.api.checklist_inbox.get_checklist", return_value={"name": "CHK-LOCK-1"}),
			patch("phamos.phamos.doctype.checklist.checklist.update_checklist_item") as update_item,
		):
			with self.assertRaises(FieldLockedError):
				update_spa_checklist_item("CHK-LOCK-1", "row-1", '{"note": "<p>x</p>"}')
			update_item.assert_not_called()
			# Other rows and other fields of the same row stay editable.
			update_spa_checklist_item("CHK-LOCK-1", "row-2", {"note": "<p>x</p>"})
			update_spa_checklist_item("CHK-LOCK-1", "row-1", {"done": 1})
			self.assertEqual(update_item.call_count, 2)
