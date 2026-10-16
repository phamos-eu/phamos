# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Event → Mailcow (SOGo) calendar sync (#1558). SOGo is replaced by patched `requests` calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.mailcow_integration.caldav import client
from phamos.mailcow_integration.caldav import sync_event

OWNER = "mc-owner@example.com"
OTHER = "mc-other@example.com"
BASE_URL = "https://mail.example.com"


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")


def _response(status):
	return SimpleNamespace(status_code=status, text="")


class TestMailcowEventSync(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_ensure_user(OWNER)
		_ensure_user(OTHER)
		self.put = MagicMock(return_value=_response(201))
		self.delete = MagicMock(return_value=_response(204))
		self.passwords = {OWNER: "owner-pw", OTHER: "other-pw"}
		for patcher in (
			patch.object(client.requests, "put", self.put),
			patch.object(client.requests, "delete", self.delete),
			patch.object(client, "settings", lambda: SimpleNamespace(base_url=BASE_URL)),
			patch.object(client, "dav_password", lambda email: self.passwords.get(email)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _event(self, **values):
		frappe.set_user(OWNER)
		doc = frappe.get_doc(
			{
				"doctype": "Event",
				"subject": "Sync test",
				"event_type": "Private",
				"starts_on": "2026-10-20 09:00:00",
				"ends_on": "2026-10-20 10:00:00",
				**values,
			}
		)
		doc.flags.mailcow_sync_now = True
		doc.insert()
		return doc

	def _headers(self, call):
		return call.kwargs["headers"]

	def test_new_event_is_pushed_once_and_create_only(self):
		doc = self._event()
		self.assertEqual(self.put.call_count, 1)  # no second push from an after_insert hook
		call = self.put.call_args
		self.assertEqual(call.args[0], f"{BASE_URL}/SOGo/dav/{OWNER}/Calendar/personal/{doc.name}.ics")
		self.assertEqual(self._headers(call).get("If-None-Match"), "*")
		self.assertEqual(frappe.db.get_value("Event", doc.name, "custom_mailcow_synched"), 1)

	def test_update_is_sent_without_precondition(self):
		doc = self._event()
		doc.reload()
		doc.subject = "Moved"
		doc.flags.mailcow_sync_now = True
		doc.save()
		self.assertEqual(self.put.call_count, 2)
		self.assertNotIn("If-None-Match", self._headers(self.put.call_args))
		self.assertEqual(frappe.db.get_value("Event", doc.name, "custom_mailcow_seq"), 2)

	def test_marker_uid_updates_the_existing_object(self):
		self._event(description="Proposal [MAILCOW-UID: abc123]")
		call = self.put.call_args
		self.assertTrue(call.args[0].endswith("/abc123.ics"))
		self.assertNotIn("If-None-Match", self._headers(call))

	def test_someone_else_saving_pushes_to_the_owners_calendar(self):
		doc = self._event()
		frappe.set_user("Administrator")
		self.assertEqual(sync_event.push_event(doc.name), None)
		self.assertIn(f"/dav/{OWNER}/", self.put.call_args.args[0])

	def test_missing_password_is_kept_on_the_event_and_cleared_later(self):
		del self.passwords[OWNER]
		doc = self._event()
		self.put.assert_not_called()
		error = frappe.db.get_value("Event", doc.name, sync_event.SYNC_ERROR_FIELD)
		self.assertIn("No DAV app password", error)
		self.passwords[OWNER] = "owner-pw"
		self.assertIsNone(sync_event.push_event(doc.name))
		self.assertEqual(frappe.db.get_value("Event", doc.name, sync_event.SYNC_ERROR_FIELD), "")

	def test_sogo_refusal_is_reported(self):
		self.put.return_value = _response(412)
		doc = self._event()
		self.assertIn("412", frappe.db.get_value("Event", doc.name, sync_event.SYNC_ERROR_FIELD))
		self.assertFalse(frappe.db.get_value("Event", doc.name, "custom_mailcow_synched"))

	def test_save_enqueues_one_job_after_commit(self):
		frappe.set_user(OWNER)
		with patch.object(sync_event.frappe, "enqueue") as enqueue:
			doc = frappe.get_doc(
				{
					"doctype": "Event",
					"subject": "Queued",
					"event_type": "Private",
					"starts_on": "2026-10-20 09:00:00",
				}
			).insert()
		self.put.assert_not_called()
		enqueue.assert_called_once()
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])
		self.assertEqual(enqueue.call_args.kwargs["event_name"], doc.name)

	def test_skip_flag_pushes_nothing(self):
		frappe.set_user(OWNER)
		doc = frappe.get_doc(
			{"doctype": "Event", "subject": "Pulled", "event_type": "Private", "starts_on": "2026-10-20 09:00:00"}
		)
		doc.flags.skip_mailcow_push = True
		with patch.object(sync_event.frappe, "enqueue") as enqueue:
			doc.insert()
		enqueue.assert_not_called()
		self.put.assert_not_called()

	def test_delete_uses_the_owners_calendar(self):
		doc = self._event()
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Event", doc.name)
		doc.flags.mailcow_sync_now = True
		doc.delete()
		self.assertEqual(self.delete.call_count, 1)
		self.assertIn(f"/dav/{OWNER}/Calendar/personal/{doc.name}.ics", self.delete.call_args.args[0])
		self.assertEqual(self.delete.call_args.kwargs["auth"], (OWNER, "owner-pw"))

	def test_weekly_rule_without_weekday_uses_the_start_day(self):
		doc = frappe.get_doc(
			{
				"doctype": "Event",
				"repeat_this_event": 1,
				"repeat_on": "Weekly",
				"starts_on": "2026-10-21 09:00:00",  # a Wednesday
			}
		)
		self.assertEqual(sync_event._event_recurrence_rule(doc), "FREQ=WEEKLY;BYDAY=WE")
