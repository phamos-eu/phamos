# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Focus mode of the Personal Cockpit (#1556), with users who are not System Managers."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime, now_datetime

from phamos.api import personal_cockpit as pc
from phamos.api import personal_focus as focus
from phamos.cockpits import permissions

USER = "fc-a@example.com"
OTHER = "fc-b@example.com"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


class TestFocusMode(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		self.todos = [self._todo(f"Focus item {i}") for i in range(3)]
		self.now = now_datetime()
		self.clock = patch.object(focus, "now_datetime", side_effect=lambda: self.now)
		self.clock.start()
		self.addCleanup(self.clock.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _todo(self, description, user=USER):
		return frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "description": description}).insert(
			ignore_permissions=True
		)

	def _names(self, count=3):
		return [t.name for t in self.todos[:count]]

	def _advance(self, minutes):
		self.now = self.now + timedelta(minutes=minutes)

	def test_start_makes_the_first_todo_current(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(), 25)
		self.assertEqual(session["current_todo"], self.todos[0].name)
		self.assertEqual([i["todo"] for i in session["items"]], self._names())
		self.assertEqual(pc.get_active_focus()["name"], session["name"])

	def test_only_one_session_at_a_time(self):
		frappe.set_user(USER)
		pc.start_focus(self._names(1), 25)
		with self.assertRaises(frappe.ValidationError):
			pc.start_focus(self._names(1), 25)

	def test_limits(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.start_focus([], 25)
		with self.assertRaises(frappe.ValidationError):
			pc.start_focus(self._names(1), 3)
		with self.assertRaises(frappe.ValidationError):
			pc.start_focus(self._names(1), 500)
		extra = [self._todo(f"More {i}").name for i in range(3)]
		with self.assertRaises(frappe.ValidationError):
			pc.start_focus(self._names() + extra, 25)

	def test_someone_elses_todo_cannot_be_focused(self):
		theirs = self._todo("Theirs", user=OTHER)
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			pc.start_focus([theirs.name], 25)

	def test_done_closes_the_todo_books_time_and_advances(self):
		frappe.set_user(USER)
		pc.start_focus(self._names(2), 25)
		self._advance(12)
		session = pc.focus_mark_done(self.todos[0].name)
		self.assertEqual(frappe.db.get_value("ToDo", self.todos[0].name, "status"), "Closed")
		self.assertEqual(frappe.db.get_value("ToDo", self.todos[0].name, "cockpit_actual_minutes"), 12)
		self.assertEqual(session["current_todo"], self.todos[1].name)
		self.assertEqual(session["status"], "Active")

	def test_last_done_completes_the_session(self):
		frappe.set_user(USER)
		pc.start_focus(self._names(2), 25)
		pc.focus_mark_done(self.todos[0].name)
		session = pc.focus_mark_done(self.todos[1].name)
		self.assertEqual((session["status"], session["outcome"]), ("Ended", "Completed"))
		self.assertIsNone(pc.get_active_focus())

	def test_park_keeps_a_resume_note_and_moves_on(self):
		frappe.set_user(USER)
		pc.start_focus(self._names(2), 25)
		session = pc.focus_park(self.todos[0].name, "Continue at step 3")
		self.assertEqual(session["current_todo"], self.todos[1].name)
		self.assertTrue(session["items"][0]["parked"])
		self.assertEqual(frappe.db.get_value("ToDo", self.todos[0].name, "cockpit_resume_note"), "Continue at step 3")
		session = pc.focus_switch(self.todos[0].name)
		self.assertFalse(session["items"][0]["parked"])

	def test_switch_books_time_on_the_previous_todo(self):
		frappe.set_user(USER)
		pc.start_focus(self._names(2), 50)
		self._advance(7)
		pc.focus_switch(self.todos[1].name)
		self._advance(5)
		session = pc.focus_switch(self.todos[0].name)
		minutes = {i["todo"]: i["minutes"] for i in session["items"]}
		self.assertEqual(minutes, {self.todos[0].name: 7, self.todos[1].name: 5})

	def test_break_out_is_never_refused_and_waits_grow(self):
		frappe.set_user(USER)
		waits = []
		for _ in range(3):
			session = pc.start_focus(self._names(1), 25)
			waits.append(session["break_out_wait_seconds"])
			ended = pc.end_focus("Broke out", reason="Customer call", resume_note="Halfway through")
			self.assertEqual((ended["status"], ended["outcome"]), ("Ended", "Broke out"))
		self.assertEqual(waits, [10, 20, 40])
		self.assertEqual(frappe.db.get_value("ToDo", self.todos[0].name, "cockpit_resume_note"), "Halfway through")
		self.assertIsNone(pc.end_focus())  # nothing running: still no error
		self.assertEqual(focus.break_out_wait_seconds(10), focus.BREAK_OUT_MAX_SECONDS)

	def test_expired_sessions_end(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(1), 25)
		self._advance(25 + focus.FOCUS_GRACE_MINUTES + 1)
		self.assertIsNone(pc.get_active_focus())
		self.assertEqual(frappe.db.get_value("Focus Session", session["name"], "outcome"), "Expired")

	def test_stopwatch_has_no_planned_end(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(1), 0)
		self.assertIsNone(session["planned_end"])
		self._advance(120)
		self.assertIsNotNone(pc.get_active_focus())

	def test_sessions_are_private_even_for_system_managers(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(1), 25)
		frappe.set_user(OTHER)
		self.assertNotIn(session["name"], frappe.get_list("Focus Session", pluck="name"))
		self.assertFalse(frappe.has_permission("Focus Session", "read", doc=session["name"]))
		with self.assertRaises(frappe.PermissionError):
			pc.get_focus_session(session["name"])
		self.assertIsNone(pc.get_active_focus())
		self.assertEqual(permissions.focus_session_query("Administrator"), "")

	def test_deleting_a_focused_todo_keeps_the_session(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(2), 25)
		frappe.set_user("Administrator")
		frappe.delete_doc("ToDo", self.todos[0].name)
		doc = frappe.get_doc("Focus Session", session["name"])
		self.assertEqual([row.todo for row in doc.items], [self.todos[1].name])
		self.assertFalse(doc.current_todo)

	def test_planned_end_follows_minutes(self):
		frappe.set_user(USER)
		session = pc.start_focus(self._names(1), 50)
		self.assertEqual(get_datetime(session["planned_end"]) - get_datetime(session["started_at"]), timedelta(minutes=50))
