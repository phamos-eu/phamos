# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Leave Application → all-day Event in the employee's calendar (milestone 68, Phase 2).

Most tests call the hook with an unsaved Leave Application, because HRMS validation needs a
holiday list, leave balances and more that a dev site may lack; one test checks the real
hook wiring and skips when the site cannot save a Leave Application. SOGo is replaced by
patched `requests` calls, as in test_mailcow_sync_event.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.mailcow_integration.caldav import client, sync_event
from phamos.phamos.hr import leave_calendar
from phamos.tests.test_mailcow_sync_event import _ensure_status_field, _ensure_user
from phamos.tests.test_personal_checkin import _ensure_employee

EMPLOYEE_USER = "lc-employee@example.com"
OTHER_USER = "lc-other@example.com"
HR_USER = "lc-hr@example.com"
BASE_URL = "https://mail.example.com"
LEAVE_NAME = "HR-LAP-TEST-LC-0001"


def _response(status):
	return SimpleNamespace(status_code=status, text="")


@unittest.skipUnless(frappe.db.exists("DocType", "Leave Application"), "HRMS is not installed")
class TestLeaveCalendar(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (EMPLOYEE_USER, OTHER_USER, HR_USER):
			_ensure_user(user)
		_ensure_status_field()
		self.employee = _ensure_employee(EMPLOYEE_USER)
		self.other_employee = _ensure_employee(OTHER_USER)
		self.put = MagicMock(return_value=_response(201))
		self.delete = MagicMock(return_value=_response(204))
		self.passwords = {EMPLOYEE_USER: "pw-1", OTHER_USER: "pw-2"}
		for patcher in (
			patch.object(client.requests, "put", self.put),
			patch.object(client.requests, "delete", self.delete),
			patch.object(client, "settings", lambda: SimpleNamespace(base_url=BASE_URL)),
			patch.object(client, "dav_password", lambda email: self.passwords.get(email)),
		):
			patcher.start()
			self.addCleanup(patcher.stop)
		# The Event's reference link must point at an existing row; db_insert skips HRMS
		# validation and hooks (rolled back in tearDown).
		if not frappe.db.exists("Leave Application", LEAVE_NAME):
			self._leave().db_insert()
		frappe.flags.mailcow_sync_now = True
		self.addCleanup(setattr, frappe.flags, "mailcow_sync_now", False)
		frappe.set_user(HR_USER)  # leave is usually entered or approved by someone else

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	# --- helpers -------------------------------------------------------------------------

	def _leave(self, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"employee_name": "LC Employee",
				"leave_type": "Leave Without Pay",
				"from_date": "2026-11-03",
				"to_date": "2026-11-05",
				"status": "Open",
				**values,
			}
		)
		doc.name = LEAVE_NAME
		doc.docstatus = values.get("docstatus", 0)
		return doc

	def _events(self):
		return frappe.get_all(
			"Event",
			filters={"reference_doctype": "Leave Application", "reference_docname": LEAVE_NAME},
			fields=["name", "owner", "subject", "all_day", "starts_on", "ends_on", "event_type",
					"send_reminder", "custom_mailcow_status", "custom_mailcow_synched",
					"custom_mailcow_sync_error"],
		)

	def _body(self, call=None):
		call = call or self.put.call_args
		return call.kwargs["data"].decode("utf-8")

	# --- draft ---------------------------------------------------------------------------

	def test_draft_creates_one_tentative_all_day_event_in_the_employees_calendar(self):
		leave_calendar.sync_leave_event(self._leave())
		events = self._events()
		self.assertEqual(len(events), 1)
		event = events[0]
		self.assertEqual(event.owner, EMPLOYEE_USER)  # not HR_USER, who saved it
		self.assertEqual(event.all_day, 1)
		self.assertEqual(event.event_type, "Private")
		self.assertEqual(event.send_reminder, 0)
		self.assertEqual(event.custom_mailcow_status, "TENTATIVE")
		self.assertEqual(event.subject, "Absent (requested)")
		self.assertEqual(self.put.call_count, 1)
		self.assertIn(f"/SOGo/dav/{EMPLOYEE_USER}/Calendar/personal/", self.put.call_args.args[0])
		body = self._body()
		self.assertIn("DTSTART;VALUE=DATE:20261103", body)
		self.assertIn("DTEND;VALUE=DATE:20261106", body)
		self.assertIn("STATUS:TENTATIVE", body)
		self.assertIn("METHOD:PUBLISH", body)
		self.assertIn(f"ORGANIZER;CN={EMPLOYEE_USER}", body)
		self.assertIn("URL:", body)
		self.assertIn(f"leave-application/{LEAVE_NAME}", body)

	def test_neither_leave_type_nor_reason_reaches_sogo(self):
		# #1720, PM Review: shared SOGo calendars must not show "Sick Leave" or the reason
		leave_calendar.sync_leave_event(self._leave(leave_type="Leave Without Pay", description="Erkältung"))
		body = self._body()
		self.assertNotIn("Leave Without Pay", body)
		self.assertNotIn("Erk", body)
		self.assertNotIn("LC Employee", body)
		self.assertIn("SUMMARY:Absent (requested)", body)

	def test_half_day_is_named_with_its_date_on_a_longer_leave(self):
		leave_calendar.sync_leave_event(self._leave(half_day=1, half_day_date="2026-11-04"))
		subject = self._events()[0].subject
		self.assertTrue(subject.startswith("Absent (requested, half day on "), subject)

	def test_half_day_on_a_single_day_has_no_date(self):
		leave_calendar.sync_leave_event(self._leave(to_date="2026-11-03", half_day=1, half_day_date="2026-11-03"))
		self.assertEqual(self._events()[0].subject, "Absent (requested, half day)")

	def test_changed_dates_update_the_same_event_without_precondition(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.sync_leave_event(self._leave(to_date="2026-11-06"))
		self.assertEqual(len(self._events()), 1)
		self.assertEqual(self.put.call_count, 2)
		self.assertNotIn("If-None-Match", self.put.call_args.kwargs["headers"])
		self.assertIn("DTEND;VALUE=DATE:20261107", self._body())

	def test_unchanged_save_pushes_nothing_more(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.sync_leave_event(self._leave())
		self.assertEqual(self.put.call_count, 1)

	# --- submit, reject, cancel, delete --------------------------------------------------

	def test_approved_and_submitted_is_confirmed_with_the_final_title(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.sync_leave_event(self._leave(status="Approved", docstatus=1))
		event = self._events()[0]
		self.assertEqual(event.subject, "Absent")
		self.assertEqual(event.custom_mailcow_status, "CONFIRMED")
		self.assertIn("STATUS:CONFIRMED", self._body())

	def test_rejected_at_submit_removes_the_event(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.sync_leave_event(self._leave(status="Rejected", docstatus=1))
		self.assertEqual(self._events(), [])
		self.assertEqual(self.delete.call_count, 1)
		self.assertIn(f"/SOGo/dav/{EMPLOYEE_USER}/", self.delete.call_args.args[0])

	def test_cancelled_removes_the_event(self):
		leave_calendar.sync_leave_event(self._leave(status="Approved", docstatus=1))
		leave_calendar.sync_leave_event(self._leave(status="Cancelled", docstatus=2))
		self.assertEqual(self._events(), [])
		self.assertEqual(self.delete.call_count, 1)

	def test_deleting_the_draft_removes_the_event(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.remove_leave_event(self._leave())
		self.assertEqual(self._events(), [])
		self.assertEqual(self.delete.call_count, 1)

	# --- other employee, no user, no password ---------------------------------------------

	def test_changed_employee_moves_the_event_to_the_new_mailbox(self):
		leave_calendar.sync_leave_event(self._leave())
		leave_calendar.sync_leave_event(self._leave(employee=self.other_employee))
		events = self._events()
		self.assertEqual(len(events), 1)
		self.assertEqual(events[0].owner, OTHER_USER)
		self.assertIn(f"/SOGo/dav/{EMPLOYEE_USER}/", self.delete.call_args.args[0])
		last_put = self.put.call_args
		self.assertIn(f"/SOGo/dav/{OTHER_USER}/", last_put.args[0])
		self.assertEqual(last_put.kwargs["headers"].get("If-None-Match"), "*")

	def test_employee_without_user_gets_no_event(self):
		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", self.employee, "user_id", None)
		frappe.set_user(HR_USER)
		leave_calendar.sync_leave_event(self._leave())
		self.assertEqual(self._events(), [])
		self.put.assert_not_called()

	def test_missing_dav_password_is_kept_on_the_event(self):
		self.passwords.pop(EMPLOYEE_USER)
		leave_calendar.sync_leave_event(self._leave())
		event = self._events()[0]
		self.assertIn("No DAV app password", event.custom_mailcow_sync_error)
		# a later save retries even without other changes
		self.passwords[EMPLOYEE_USER] = "pw-1"
		leave_calendar.sync_leave_event(self._leave())
		event = self._events()[0]
		self.assertEqual(event.custom_mailcow_sync_error, "")
		self.assertEqual(event.custom_mailcow_synched, 1)

	def test_save_enqueues_the_push_after_commit(self):
		frappe.flags.mailcow_sync_now = False
		with patch.object(leave_calendar.frappe, "enqueue") as enqueue:
			leave_calendar.sync_leave_event(self._leave())
		self.put.assert_not_called()
		enqueue.assert_called_once()
		self.assertEqual(enqueue.call_args.args[0], leave_calendar.PUSH_METHOD)
		self.assertTrue(enqueue.call_args.kwargs["enqueue_after_commit"])

	# --- form state ------------------------------------------------------------------------

	def test_calendar_state_for_the_form(self):
		self.passwords.pop(EMPLOYEE_USER)
		leave = self._leave()
		leave_calendar.sync_leave_event(leave)
		frappe.set_user("Administrator")
		with patch.object(leave_calendar.frappe, "get_doc", side_effect=lambda *a, **k: leave):
			with patch.object(leave, "check_permission"):
				state = leave_calendar.get_calendar_state(LEAVE_NAME)
		self.assertEqual(state["user"], EMPLOYEE_USER)
		self.assertEqual(state["reason"], "error")
		self.assertIn("No DAV app password", state["error"])
		self.assertFalse(state["synced"])

	# --- real hook wiring -------------------------------------------------------------------

	def test_saving_a_real_draft_runs_the_hook(self):
		frappe.set_user("Administrator")
		# HRMS needs a holiday list to count leave days; a temporary one (rolled back).
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "LC Test Holidays",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
			}
		).insert(ignore_permissions=True, ignore_if_duplicate=True)
		frappe.db.set_value("Employee", self.employee, "holiday_list", holiday_list.name)
		doc = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.employee,
				"leave_type": "Leave Without Pay",
				"from_date": "2026-12-08",  # clear of the stub leave in setUp
				"to_date": "2026-12-09",
				"status": "Open",
			}
		)
		try:
			doc.insert(ignore_permissions=True)
		except frappe.ValidationError as e:
			self.skipTest(f"this site cannot save a Leave Application: {e}")
		rows = frappe.get_all(
			"Event", filters={"reference_doctype": "Leave Application", "reference_docname": doc.name},
			fields=["owner", "custom_mailcow_status"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].owner, EMPLOYEE_USER)
		self.assertEqual(rows[0].custom_mailcow_status, "TENTATIVE")
