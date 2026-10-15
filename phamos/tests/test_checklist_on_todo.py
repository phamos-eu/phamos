# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Checklists on ToDos in the Personal Cockpit (#1554), with users who are not System Managers.

USER_A has "Support Team", which on our sites may create and edit Checklists but not delete
them; USER_C has no Checklist permission at all.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import checklist_inbox
from phamos.api import department_cockpit as dc
from phamos.api import personal_cockpit as pc
from phamos.cockpits.maintenance import cleanup_orphan_todo_checklists

USER_A = "chk-a@example.com"
USER_B = "chk-b@example.com"
USER_C = "chk-c@example.com"


def _ensure_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)
	return email


def _ensure_checklist_role():
	"""Our sites grant Checklist create/write to Support Team via Custom DocPerm."""
	if not frappe.db.exists("Custom DocPerm", {"parent": "Checklist", "role": "Support Team", "create": 1}):
		from frappe.permissions import add_permission, update_permission_property

		add_permission("Checklist", "Support Team", 0)
		for ptype in ("read", "write", "create"):
			update_permission_property("Checklist", "Support Team", 0, ptype, 1)


def _todo(user, description):
	return frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "description": description}).insert(
		ignore_permissions=True
	)


class TestChecklistOnToDo(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_checklist_role()
		_ensure_user(USER_A, ("Employee", "Support Team"))
		_ensure_user(USER_B, ("Employee", "Support Team"))
		_ensure_user(USER_C, ("Employee",))
		self.mine = _todo(USER_A, "<p>Prepare the workshop</p><p>agenda, room</p>")
		self.theirs = _todo(USER_B, "Their ToDo")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _create(self, todo_name, **kwargs):
		return pc.create_checklist("ToDo", todo_name, items=[{"description": "Book the room"}], **kwargs)

	def test_create_on_my_todo_and_list_it(self):
		frappe.set_user(USER_A)
		checklist = self._create(self.mine.name, name="Workshop prep")
		names = {row["name"] for row in pc.get_checklists(include_completed=1)["items"]}
		self.assertIn(checklist["name"], names)
		linked = checklist_inbox.get_checklists_for_reference("ToDo", self.mine.name)
		self.assertEqual([row["name"] for row in linked], [checklist["name"]])

	def test_title_falls_back_to_the_todo_summary(self):
		frappe.set_user(USER_A)
		checklist = self._create(self.mine.name)
		self.assertEqual(frappe.db.get_value("Checklist", checklist["name"], "title"), "Prepare the workshop")

	def test_someone_elses_todo_is_refused(self):
		frappe.set_user(USER_A)
		with self.assertRaises(frappe.ValidationError):
			self._create(self.theirs.name, name="Not mine")

	def test_reference_search_offers_my_open_todos(self):
		frappe.set_user(USER_A)
		rows = dc.checklist_reference_query(pc.CONFIG, "ToDo", "workshop", "name", 0, 20, {})
		self.assertEqual(rows, [[self.mine.name, "Prepare the workshop"]])
		self.assertEqual(dc.checklist_reference_query(pc.CONFIG, "ToDo", "Their", "name", 0, 20, {}), [])

	def test_user_without_checklist_permission_gets_a_permission_error(self):
		todo = _todo(USER_C, "No checklist rights")
		frappe.set_user(USER_C)
		with self.assertRaises(frappe.PermissionError):
			checklist_inbox.get_checklists_for_reference("ToDo", todo.name)

	def test_deleting_the_todo_removes_its_checklists(self):
		frappe.set_user(USER_A)
		checklist = self._create(self.mine.name, name="Goes with the ToDo")
		frappe.delete_doc("ToDo", self.mine.name)  # Support Team cannot delete Checklists itself
		self.assertFalse(frappe.db.exists("Checklist", checklist["name"]))

	def test_orphans_are_cleaned_up(self):
		frappe.set_user(USER_A)
		checklist = self._create(self.mine.name, name="Orphan")
		frappe.set_user("Administrator")
		frappe.db.delete("ToDo", {"name": self.mine.name})  # like delete_dynamic_links: no hooks
		with patch("frappe.db.commit"):
			self.assertEqual(cleanup_orphan_todo_checklists(), 1)
		self.assertFalse(frappe.db.exists("Checklist", checklist["name"]))
