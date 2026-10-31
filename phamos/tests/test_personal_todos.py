# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Personal Cockpit ToDos (#1541): my list, order, create rules, close and reopen."""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from phamos.api import personal_cockpit as pc
from phamos.api import personal_todos

USER_A = "todo-a@example.com"
USER_B = "todo-b@example.com"
ROLES = ("System Manager", "Support Team", "Projects User")


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(ROLES) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)
	return email


def _todo(user, description, date=None, priority="Medium", status="Open", **extra):
	return frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"description": description,
			"date": date,
			"priority": priority,
			"status": status,
			**extra,
		}
	).insert(ignore_permissions=True)


class TestSortOrder(FrappeTestCase):
	def test_due_date_first_then_priority_then_age_and_undated_last(self):
		rows = [
			{"name": "undated-high", "date": None, "priority": "High", "creation": "2026-01-01"},
			{"name": "later-high", "date": "2026-10-20", "priority": "High", "creation": "2026-01-01"},
			{"name": "soon-low", "date": "2026-10-15", "priority": "Low", "creation": "2026-01-01"},
			{"name": "soon-high-new", "date": "2026-10-15", "priority": "High", "creation": "2026-03-01"},
			{"name": "soon-high-old", "date": "2026-10-15", "priority": "High", "creation": "2026-02-01"},
		]
		self.assertEqual(
			[r["name"] for r in sorted(rows, key=personal_todos.sort_key)],
			["soon-high-old", "soon-high-new", "soon-low", "later-high", "undated-high"],
		)


class TestMyTodos(FrappeTestCase):
	def setUp(self):
		# Assigning notifies the assignee; in tests that e-mail commits the transaction.
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)

		frappe.set_user("Administrator")
		_ensure_user(USER_A)
		_ensure_user(USER_B)
		self.mine = _todo(USER_A, "<p>Call the customer</p><p>details</p>", date=today(), priority="High")
		self.closed = _todo(USER_A, "Already done", status="Closed")
		self.cancelled = _todo(USER_A, "Was cancelled", status="Cancelled")
		self.theirs = _todo(USER_B, "Not mine")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _names(self, **kwargs):
		return [row["name"] for row in pc.get_my_todos(**kwargs)]

	def test_lists_only_my_open_todos(self):
		frappe.set_user(USER_A)
		names = self._names()
		self.assertIn(self.mine.name, names)
		self.assertNotIn(self.closed.name, names)
		self.assertNotIn(self.cancelled.name, names)
		self.assertNotIn(self.theirs.name, names)

	def test_closed_ones_on_request_but_never_cancelled(self):
		frappe.set_user(USER_A)
		names = self._names(include_closed=1)
		self.assertIn(self.closed.name, names)
		self.assertNotIn(self.cancelled.name, names)

	def test_row_has_summary_and_links(self):
		frappe.set_user(USER_A)
		row = pc.get_todo(self.mine.name)
		self.assertEqual(row["summary"], "Call the customer")
		self.assertEqual(row["desk_url"], f"/app/todo/{self.mine.name}")
		self.assertFalse(row["overdue"])

	def test_someone_elses_todo_is_refused(self):
		frappe.set_user(USER_A)
		for call in (
			lambda: pc.get_todo(self.theirs.name),
			lambda: pc.update_todo(self.theirs.name, priority="Low"),
			lambda: pc.close_todo(self.theirs.name),
		):
			with self.assertRaises(frappe.PermissionError):
				call()

	def test_create_without_reference(self):
		frappe.set_user(USER_A)
		row = pc.create_todo("<p>Prepare the offer</p>", date=add_days(today(), 2), priority="Low")
		self.assertEqual(row["summary"], "Prepare the offer")
		self.assertEqual(row["priority"], "Low")
		self.assertIsNone(row["reference_type"])
		self.assertEqual(frappe.db.get_value("ToDo", row["name"], "allocated_to"), USER_A)

	def test_create_rejects_a_past_date_and_empty_text(self):
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			pc.create_todo("Too late", date=add_days(today(), -1))
		with self.assertRaises(frappe.ValidationError):
			pc.create_todo("<p> </p>")

	def test_create_with_reference_assigns_me_on_the_record(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "ToDo reference"}).insert(ignore_permissions=True)
		frappe.set_user(USER_A)
		row = pc.create_todo("Follow up", reference_type="Issue", reference_name=issue.name)
		self.assertEqual(row["reference_title"], "ToDo reference")
		self.assertEqual(row["reference_url"], f"/app/issue/{issue.name}")
		self.assertIn(USER_A, json.loads(frappe.db.get_value("Issue", issue.name, "_assign") or "[]"))

	def test_create_rejects_half_a_reference_and_other_doctypes(self):
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			pc.create_todo("Half", reference_type="Issue")
		with self.assertRaises(frappe.ValidationError):
			pc.create_todo("Other", reference_type="User", reference_name=USER_B)

	def test_update_keeps_an_overdue_date_unless_it_is_changed(self):
		overdue = _todo(USER_A, "Overdue", date=add_days(today(), -3))
		frappe.set_user(USER_A)
		row = pc.update_todo(overdue.name, priority="High")
		self.assertTrue(row["overdue"])
		with self.assertRaises(frappe.ValidationError):
			pc.update_todo(overdue.name, date=add_days(today(), -1))
		self.assertFalse(pc.update_todo(overdue.name, date=today())["overdue"])

	def test_closing_an_assignment_removes_me_from_the_record_and_reopening_adds_me(self):
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Assigned"}).insert(ignore_permissions=True)
		from frappe.desk.form.assign_to import add as add_assignment

		add_assignment({"doctype": "Issue", "name": issue.name, "assign_to": [USER_A], "description": "x"})
		todo = frappe.get_value("ToDo", {"reference_name": issue.name, "allocated_to": USER_A})

		frappe.set_user(USER_A)
		self.assertEqual(pc.close_todo(todo)["status"], "Closed")
		self.assertNotIn(USER_A, json.loads(frappe.db.get_value("Issue", issue.name, "_assign") or "[]"))
		self.assertEqual(pc.reopen_todo(todo)["status"], "Open")
		self.assertIn(USER_A, json.loads(frappe.db.get_value("Issue", issue.name, "_assign") or "[]"))

	def test_reference_types_are_installed_doctypes(self):
		frappe.set_user(USER_A)
		types = pc.get_todo_reference_types()
		self.assertIn("Issue", types)
		self.assertTrue(set(types) <= set(personal_todos.CREATE_REFERENCE_TYPES))
