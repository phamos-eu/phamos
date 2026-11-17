# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Event → Mailcow (SOGo) calendar sync (#1558) and the milestone-68 groundwork: all-day
events, STATUS, URL, METHOD, the owner as organizer, `pull_event_slots` all-day flag and timeout,
and the slot cache. SOGo is replaced by patched `requests` calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.mailcow_integration.caldav import client
from phamos.mailcow_integration.caldav import sync_event
from phamos.mailcow_integration.caldav import slot_cache

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


def _ensure_status_field():
	"""The fixture adds `custom_mailcow_status`; a test site that has not migrated it yet gets it here."""
	if frappe.get_meta("Event").has_field("custom_mailcow_status"):
		return
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

	create_custom_fields(
		{
			"Event": [
				{
					"fieldname": "custom_mailcow_status",
					"label": "Calendar Status",
					"fieldtype": "Select",
					"options": "\nCONFIRMED\nTENTATIVE",
					"insert_after": "custom_mailcow_sync_error",
					"hidden": 1,
					"read_only": 1,
					"no_copy": 1,
				}
			]
		},
		ignore_validate=True,
	)
	frappe.clear_cache(doctype="Event")


MULTISTATUS = """<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
<D:response><D:href>/SOGo/dav/x/Calendar/personal/leave-1.ics</D:href><D:propstat><D:prop>
<C:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:leave-1
DTSTAMP:20261001T000000Z
DTSTART;VALUE=DATE:20261103
DTEND;VALUE=DATE:20261106
SUMMARY:Leave: Vacation
END:VEVENT
END:VCALENDAR
</C:calendar-data></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
<D:response><D:href>/SOGo/dav/x/Calendar/personal/meet-1.ics</D:href><D:propstat><D:prop>
<C:calendar-data>BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:meet-1
DTSTAMP:20261001T000000Z
DTSTART:20261104T090000Z
DTEND:20261104T100000Z
SUMMARY:Standup
END:VEVENT
END:VCALENDAR
</C:calendar-data></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat></D:response>
</D:multistatus>"""


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
			patch.object(sync_event, "settings", lambda: SimpleNamespace(base_url=BASE_URL)),
			patch.object(client, "dav_password", lambda email: self.passwords.get(email)),
			# pull_event_slots looks the password up through its own module namespace
			patch.object(sync_event, "dav_password", lambda email: self.passwords.get(email)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		_ensure_status_field()
		slot_cache.invalidate(OWNER)

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

	# --- milestone 68, Phase 0: all-day, status, url, method, organizer ---------------------

	def _body(self):
		return self.put.call_args.kwargs["data"].decode("utf-8")

	def test_all_day_event_uses_date_values_with_an_exclusive_end(self):
		self._event(all_day=1, starts_on="2026-11-03 00:00:00", ends_on="2026-11-05 23:59:59")
		body = self._body()
		self.assertIn("DTSTART;VALUE=DATE:20261103", body)
		self.assertIn("DTEND;VALUE=DATE:20261106", body)
		self.assertNotIn("TZID", body)

	def test_timed_event_keeps_tzid_values(self):
		self._event()
		body = self._body()
		self.assertIn("DTSTART;TZID=", body)
		self.assertNotIn("VALUE=DATE", body)

	def test_status_url_and_method_without_attendees(self):
		doc = self._event(
			custom_mailcow_status="TENTATIVE", reference_doctype="User", reference_docname=OWNER
		)
		frappe.db.set_value("Event", doc.name, "custom_mailcow_status", "TENTATIVE", update_modified=False)
		sync_event.push_event(doc.name)
		body = self._body()
		self.assertIn("STATUS:TENTATIVE", body)
		self.assertIn("METHOD:PUBLISH", body)
		self.assertIn(f"URL:{frappe.utils.get_url_to_form('User', OWNER)}", body)

	def test_default_status_is_confirmed_and_attendees_make_it_a_request(self):
		self._event(custom_attendees_to=OTHER)
		body = self._body()
		self.assertIn("STATUS:CONFIRMED", body)
		self.assertIn("METHOD:REQUEST", body)
		self.assertIn(f"ATTENDEE;ROLE=OPT-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=TRUE:mailto:{OTHER}", body)
		self.assertNotIn("URL:", body)

	def test_organizer_is_the_owner_in_a_queued_push(self):
		doc = self._event()
		frappe.set_user("Administrator")  # the worker that runs the queued job
		sync_event.push_event(doc.name)
		self.assertIn(f"ORGANIZER;CN={OWNER}:mailto:{OWNER}", self._body())
		self.assertNotIn("Administrator", self._body())

	# --- pull_event_slots: all-day flag and timeout, slot cache ----------------------------

	def _report(self, status=207, content=MULTISTATUS):
		return MagicMock(return_value=SimpleNamespace(status_code=status, content=content.encode("utf-8"), text=content))

	def test_pull_event_slots_marks_all_day_and_forwards_the_timeout(self):
		frappe.set_user(OWNER)
		report = self._report()
		with patch("requests.request", report):
			slots = sync_event.pull_event_slots("2026-11-02T00:00:00", "2026-11-08T00:00:00", timeout=8)
		self.assertEqual(report.call_args.kwargs["timeout"], 8)
		by_uid = {s["uid"]: s for s in slots}
		self.assertTrue(by_uid["leave-1"]["all_day"])
		self.assertFalse(by_uid["meet-1"]["all_day"])
		self.assertEqual(by_uid["leave-1"]["start_date"], "2026-11-03")
		self.assertEqual(by_uid["leave-1"]["end_date"], "2026-11-05")  # DTEND 6 Nov is exclusive
		self.assertIsNone(by_uid["meet-1"]["start_date"])

	def test_pull_event_slots_timeout_is_clamped(self):
		frappe.set_user(OWNER)
		report = self._report()
		with patch("requests.request", report):
			sync_event.pull_event_slots("2026-11-02T00:00:00", "2026-11-08T00:00:00", timeout="0")
		self.assertEqual(report.call_args.kwargs["timeout"], 30)

	def test_slot_cache_reuses_one_report_until_refreshed_or_invalidated(self):
		frappe.set_user(OWNER)
		report = self._report()
		args = (OWNER, "2026-11-02T00:00:00", "2026-11-08T00:00:00")
		with patch("requests.request", report):
			first = slot_cache.get_slots(*args)
			slot_cache.get_slots(*args)
			self.assertEqual(report.call_count, 1)
			slot_cache.get_slots(*args, refresh=True)
			self.assertEqual(report.call_count, 2)
			slot_cache.invalidate(OWNER)
			slot_cache.get_slots(*args)
			self.assertEqual(report.call_count, 3)
		self.assertEqual([s["uid"] for s in first], ["leave-1", "meet-1"])

	def test_a_push_drops_the_owners_cached_slots(self):
		frappe.set_user(OWNER)
		args = (OWNER, "2026-11-02T00:00:00", "2026-11-08T00:00:00")
		with patch("requests.request", self._report()):
			slot_cache.get_slots(*args)
		self.assertIsNotNone(frappe.cache.get_value(slot_cache._key(*args), expires=True))
		self._event()  # pushes to OWNER's calendar
		self.assertIsNone(frappe.cache.get_value(slot_cache._key(*args), expires=True))
