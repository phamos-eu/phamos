# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Eisenhower matrix and working days for the Personal Cockpit (#1555).

"Today" is pinned to Wednesday 2026-10-14, so "urgent" means due by Friday 2026-10-16.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.api import personal_cockpit as pc
from phamos.api import personal_todo_matrix as matrix
from phamos.api import personal_todos
from phamos.cockpits import workdays

USER = "mx-a@example.com"
OTHER = "mx-b@example.com"
WEDNESDAY = "2026-10-14"


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")


class TestEisenhowerMatrix(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER)
		for module in (matrix, personal_todos):
			frozen = patch.object(module, "today", return_value=WEDNESDAY)
			frozen.start()
			self.addCleanup(frozen.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _todo(self, description, date=None, priority="Medium", user=USER, important=None):
		doc = frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"description": description,
				"date": date,
				"priority": priority,
			}
		).insert(ignore_permissions=True)
		if important is not None:
			doc.db_set("cockpit_important", int(important))
		return doc

	def _quadrant_names(self, data, key):
		return [row["summary"] for row in data["quadrants"][key]["items"]]

	# working days

	def test_add_working_days_skips_weekends(self):
		with patch.object(workdays, "_employee", return_value=None):
			self.assertEqual(workdays.add_working_days("2026-10-14", 2, USER), getdate("2026-10-16"))
			self.assertEqual(workdays.add_working_days("2026-10-15", 2, USER), getdate("2026-10-19"))
			self.assertEqual(workdays.add_working_days("2026-10-17", 0, USER), getdate("2026-10-19"))

	def test_holidays_are_not_working_days(self):
		holiday_list = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "Cockpit test holidays",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
				"holidays": [{"holiday_date": "2026-10-15", "description": "Test holiday"}],
			}
		).insert(ignore_permissions=True)
		with patch.object(workdays, "_employee", return_value="EMP-TEST"), patch.object(
			workdays, "_holiday_list", return_value=holiday_list.name
		):
			self.assertEqual(workdays.add_working_days("2026-10-14", 2, USER), getdate("2026-10-19"))

	# matrix

	def test_quadrants_follow_flag_and_due_date(self):
		self._todo("Due today, important", "2026-10-14", priority="High")
		self._todo("Overdue, important", "2026-10-01", important=1)
		self._todo("Next Thursday, important", "2026-10-22", important=1)
		self._todo("Friday, not important", "2026-10-16")
		self._todo("Undated")
		self._todo("Monday, not important", "2026-10-19")
		frappe.set_user(USER)
		data = pc.get_todo_matrix()
		self.assertEqual(data["urgent_until"], getdate("2026-10-16"))
		self.assertEqual(sorted(self._quadrant_names(data, "do")), ["Due today, important", "Overdue, important"])
		self.assertEqual(self._quadrant_names(data, "schedule"), ["Next Thursday, important"])
		self.assertEqual(self._quadrant_names(data, "delegate"), ["Friday, not important"])
		self.assertEqual(self._quadrant_names(data, "eliminate"), ["Undated"])
		self.assertEqual(data["out_of_scope"], 1)  # Monday, not important: next week
		self.assertIn("Monday, not important", self._quadrant_names(pc.get_todo_matrix("all"), "eliminate"))

	def test_only_my_open_todos(self):
		self._todo("Theirs", "2026-10-14", user=OTHER)
		closed = self._todo("Closed", "2026-10-14")
		closed.db_set("status", "Closed")
		frappe.set_user(USER)
		data = pc.get_todo_matrix("all")
		self.assertEqual(sum(q["total"] for q in data["quadrants"].values()), 0)

	def test_quadrant_lists_are_capped(self):
		for index in range(matrix.MATRIX_LIMIT + 1):
			self._todo(f"Someday {index}")
		frappe.set_user(USER)
		bucket = pc.get_todo_matrix()["quadrants"]["eliminate"]
		self.assertEqual((len(bucket["items"]), bucket["total"]), (matrix.MATRIX_LIMIT, matrix.MATRIX_LIMIT + 1))

	# moving

	def test_move_into_do_sets_flag_and_today(self):
		todo = self._todo("Undated")
		frappe.set_user(USER)
		moved = pc.set_todo_quadrant(todo.name, "do")
		self.assertEqual((moved["quadrant"], moved["important"]), ("do", True))
		self.assertEqual(getdate(moved["date"]), getdate("2026-10-14"))

	def test_urgent_date_must_be_within_the_horizon(self):
		todo = self._todo("Undated")
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.set_todo_quadrant(todo.name, "delegate", date="2026-10-20")
		self.assertEqual(getdate(pc.set_todo_quadrant(todo.name, "delegate", date="2026-10-16")["date"]), getdate("2026-10-16"))

	def test_leaving_urgent_needs_a_later_date_and_counts_as_reschedule(self):
		todo = self._todo("Due today", "2026-10-14", important=1)
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.set_todo_quadrant(todo.name, "schedule")
		with self.assertRaises(frappe.ValidationError):
			pc.set_todo_quadrant(todo.name, "schedule", date="2026-10-16")
		moved = pc.set_todo_quadrant(todo.name, "schedule", date="2026-10-21")
		self.assertEqual(moved["quadrant"], "schedule")
		self.assertEqual(moved["reschedule_count"], 1)

	def test_flag_only_move_keeps_the_date(self):
		todo = self._todo("Friday", "2026-10-16")
		frappe.set_user(USER)
		moved = pc.set_todo_quadrant(todo.name, "do")
		self.assertEqual(getdate(moved["date"]), getdate("2026-10-16"))
		self.assertEqual(moved["reschedule_count"], 0)

	def test_payoff_note_is_kept_as_comment(self):
		todo = self._todo("Undated")
		frappe.set_user(USER)
		pc.set_todo_quadrant(todo.name, "schedule", payoff_note="The customer <b>waits</b>")
		content = frappe.db.get_value(
			"Comment", {"reference_doctype": "ToDo", "reference_name": todo.name, "comment_type": "Comment"}, "content"
		)
		self.assertTrue(content.startswith(matrix.PAYOFF_PREFIX))
		self.assertNotIn("<b>", content)

	def test_someone_elses_todo_cannot_be_moved(self):
		todo = self._todo("Theirs", user=OTHER)
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			pc.set_todo_quadrant(todo.name, "do")

	def test_unknown_quadrant_is_refused(self):
		todo = self._todo("Undated")
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.set_todo_quadrant(todo.name, "later")
