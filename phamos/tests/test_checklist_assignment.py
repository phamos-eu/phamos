# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Checklist item assignee and due date (#1625): one ToDo per item, synced both ways.

USER_A, USER_B and USER_C are desk users ("Employee") without any Checklist permission: the
share that comes with an assignment is what lets them open and tick their item. EDITOR has
"Support Team", which may edit Checklists through its role.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from phamos.api import checklist_inbox
from phamos.phamos.doctype.checklist_template.checklist_template import create_checklist_from_template
from phamos.tests.test_checklist_on_todo import _ensure_checklist_role

USER_A = "chk-assign-a@example.com"
USER_B = "chk-assign-b@example.com"
USER_C = "chk-assign-c@example.com"
EDITOR = "chk-assign-editor@example.com"
PORTAL = "chk-assign-portal@example.com"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing - {"Employee"}:
		frappe.get_doc("User", email).add_roles(*(missing - {"Employee"}))
	if "Employee" in missing:
		# HRMS drops "Employee" on save from users without an Employee record, so add the row
		# directly; assignees must have this role (#1625).
		frappe.get_doc(
			{"doctype": "Has Role", "parent": email, "parenttype": "User", "parentfield": "roles", "role": "Employee"}
		).db_insert()
		# Employee gives desk access; User.save would set this, the direct insert does not.
		frappe.db.set_value("User", email, "user_type", "System User")
		frappe.clear_cache(user=email)
	return email


def _checklist(*items):
	return frappe.get_doc(
		{
			"doctype": "Checklist",
			"title": "Assignment test",
			"checklist_owner": "Administrator",
			"checklist_items": list(items),
		}
	).insert()


def _todo(row):
	return frappe.get_doc("ToDo", row.todo) if row.todo else None


def _shared_users(checklist):
	return set(
		frappe.get_all(
			"DocShare", filters={"share_doctype": "Checklist", "share_name": checklist.name}, pluck="user"
		)
	)


class TestChecklistAssignment(FrappeTestCase):
	def setUp(self):
		self.notify = patch("phamos.phamos.doctype.checklist.checklist_assignment._notify_assignee")
		self.notify_mock = self.notify.start()
		self.addCleanup(self.notify.stop)
		frappe.set_user("Administrator")
		_ensure_checklist_role()
		for user in (USER_A, USER_B, USER_C):
			_ensure_user(user)
		_ensure_user(EDITOR, ("Employee", "Support Team"))
		_ensure_user(PORTAL, ())

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_assigning_an_item_creates_a_todo_and_shares_the_checklist(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A, "due_date": "2026-10-20"})
		row = checklist.checklist_items[0]
		todo = _todo(row)

		self.assertEqual(todo.allocated_to, USER_A)
		self.assertEqual(todo.status, "Open")
		self.assertEqual((todo.reference_type, todo.reference_name), ("Checklist", checklist.name))
		self.assertEqual(getdate(todo.date), getdate("2026-10-20"))
		self.assertIn("Call back", todo.description)
		self.assertEqual(_shared_users(checklist), {USER_A})
		self.notify_mock.assert_called_once()

	def test_two_items_for_one_user_get_two_todos(self):
		checklist = _checklist(
			{"description": "One", "assigned_to": USER_A}, {"description": "Two", "assigned_to": USER_A}
		)
		first, second = checklist.checklist_items
		self.assertTrue(first.todo and second.todo)
		self.assertNotEqual(first.todo, second.todo)

	def test_checklist_due_date_is_the_latest_item_due_date(self):
		checklist = _checklist(
			{"description": "One", "due_date": "2026-10-20"},
			{"description": "Two", "due_date": "2026-11-02"},
			{"description": "Three"},
		)
		self.assertEqual(getdate(checklist.due_date), getdate("2026-11-02"))
		checklist.checklist_items[1].due_date = None
		checklist.save()
		self.assertEqual(getdate(checklist.due_date), getdate("2026-10-20"))

	def test_ticking_the_item_closes_the_todo_and_unticking_reopens_it(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A})
		row = checklist.checklist_items[0]

		checklist_inbox.update_spa_checklist_item(checklist.name, row.name, {"done": 1})
		self.assertEqual(frappe.db.get_value("ToDo", row.todo, "status"), "Closed")

		checklist_inbox.update_spa_checklist_item(checklist.name, row.name, {"done": 0})
		self.assertEqual(frappe.db.get_value("ToDo", row.todo, "status"), "Open")

	def test_closing_or_rescheduling_the_todo_updates_the_item(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A, "due_date": "2026-10-20"})
		todo = _todo(checklist.checklist_items[0])

		todo.date = "2026-10-25"
		todo.save()
		checklist.reload()
		self.assertEqual(getdate(checklist.checklist_items[0].due_date), getdate("2026-10-25"))
		self.assertEqual(getdate(checklist.due_date), getdate("2026-10-25"))

		todo.reload()
		todo.status = "Closed"
		todo.save()
		checklist.reload()
		self.assertEqual(checklist.checklist_items[0].done, 1)
		self.assertEqual(checklist.status, "Completed")

	def test_reassigning_cancels_the_old_todo_and_moves_the_share(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A})
		old_todo = checklist.checklist_items[0].todo

		checklist.checklist_items[0].assigned_to = USER_B
		checklist.save()
		row = checklist.checklist_items[0]

		self.assertEqual(frappe.db.get_value("ToDo", old_todo, "status"), "Cancelled")
		self.assertEqual(_todo(row).allocated_to, USER_B)
		self.assertEqual(_shared_users(checklist), {USER_B})

	def test_cancelling_the_todo_clears_the_assignee(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A})
		todo = _todo(checklist.checklist_items[0])

		todo.status = "Cancelled"
		todo.save()
		checklist.reload()

		self.assertFalse(checklist.checklist_items[0].assigned_to)
		self.assertFalse(checklist.checklist_items[0].todo)
		self.assertEqual(_shared_users(checklist), set())

	def test_removing_the_item_cancels_its_todo(self):
		checklist = _checklist({"description": "One", "assigned_to": USER_A}, {"description": "Two"})
		row = checklist.checklist_items[0]

		checklist_inbox.delete_spa_checklist_item(checklist.name, row.name)

		self.assertEqual(frappe.db.get_value("ToDo", row.todo, "status"), "Cancelled")
		self.assertEqual(_shared_users(checklist), set())

	def test_a_ticked_item_gets_no_todo_until_it_is_unticked(self):
		checklist = _checklist({"description": "Done already", "assigned_to": USER_A, "done": 1})
		self.assertFalse(checklist.checklist_items[0].todo)

		checklist.checklist_items[0].done = 0
		checklist.save()
		self.assertEqual(_todo(checklist.checklist_items[0]).status, "Open")

	def test_deleting_the_checklist_cancels_open_todos(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A})
		todo_name = checklist.checklist_items[0].todo

		# Hold back Frappe's own clean-up job, which deletes the ToDo right away under tests.
		with patch("frappe.enqueue"):
			frappe.delete_doc("Checklist", checklist.name)

		self.assertEqual(frappe.db.get_value("ToDo", todo_name, "status"), "Cancelled")

	def test_deleting_the_todo_clears_the_item_link(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_A})
		todo_name = checklist.checklist_items[0].todo

		frappe.delete_doc("ToDo", todo_name, ignore_permissions=True)

		self.assertFalse(frappe.db.get_value("Checklist Items", checklist.checklist_items[0].name, "todo"))

	def test_assignee_without_checklist_role_can_tick_their_item(self):
		checklist = _checklist({"description": "Call back", "assigned_to": USER_C})
		row = checklist.checklist_items[0]

		frappe.set_user(USER_C)
		payload = checklist_inbox.get_checklist(checklist.name)
		self.assertEqual(payload["items"][0]["assigned_to"], USER_C)
		checklist_inbox.update_spa_checklist_item(checklist.name, row.name, {"done": 1})

		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("ToDo", row.todo, "status"), "Closed")

	def test_user_without_employee_role_cannot_be_assigned(self):
		non_employee = _ensure_user("chk-assign-no-employee@example.com", ("Support Team",))
		with self.assertRaises(frappe.ValidationError):
			_checklist({"description": "Call back", "assigned_to": non_employee})

	def test_template_item_assignee_must_be_an_employee(self):
		non_employee = _ensure_user("chk-assign-no-employee@example.com", ("Support Team",))
		template = frappe.get_doc(
			{
				"doctype": "Checklist Template",
				"title": "Assignment template",
				"department": frappe.db.get_value("Department", {"is_group": 0}, "name"),
				"document": "Lead",
				"checklist_template_owner": "Administrator",
				"checklist_template_items": [{"description": "Step", "assigned_to": non_employee}],
			}
		)
		with self.assertRaises(frappe.ValidationError):
			template.insert()

	def test_portal_user_cannot_be_assigned(self):
		with self.assertRaises(frappe.ValidationError):
			_checklist({"description": "Call back", "assigned_to": PORTAL})

	def test_disabled_user_cannot_be_assigned(self):
		_ensure_user("chk-assign-disabled@example.com")
		frappe.db.set_value("User", "chk-assign-disabled@example.com", "enabled", 0)
		with self.assertRaises(frappe.ValidationError):
			_checklist({"description": "Call back", "assigned_to": "chk-assign-disabled@example.com"})

	def test_template_copies_assignee_and_due_in_days(self):
		template = frappe.get_doc(
			{
				"doctype": "Checklist Template",
				"title": "Assignment template",
				"department": frappe.db.get_value("Department", {"is_group": 0}, "name"),
				"document": "Lead",
				"checklist_template_owner": "Administrator",
				"checklist_template_items": [
					{"description": "In three days", "assigned_to": USER_A, "due_in_days": 3},
					{"description": "No date", "due_in_days": 0},
				],
			}
		).insert()
		template.submit()

		name = create_checklist_from_template(template.name, checklist_owner="Administrator")
		first, second = frappe.get_doc("Checklist", name).checklist_items

		self.assertEqual(first.assigned_to, USER_A)
		self.assertEqual(getdate(first.due_date), getdate(add_days(today(), 3)))
		self.assertTrue(first.todo)
		self.assertFalse(second.due_date)

	def test_a_foreign_todo_named_in_the_item_is_never_touched(self):
		"""`todo` is server-owned: naming someone else's ToDo there must not close or cancel it."""
		victim = frappe.get_doc(
			{"doctype": "ToDo", "allocated_to": USER_A, "description": "Private task"}
		).insert(ignore_permissions=True)

		checklist = _checklist({"description": "Call back", "assigned_to": USER_B, "todo": victim.name})
		self.assertNotEqual(checklist.checklist_items[0].todo, victim.name)

		checklist.checklist_items[0].todo = victim.name
		checklist.checklist_items[0].assigned_to = USER_C
		checklist.save()
		checklist.checklist_items[0].done = 1
		checklist.save()
		checklist.remove(checklist.checklist_items[0])
		checklist.save()

		self.assertEqual(frappe.db.get_value("ToDo", victim.name, "status"), "Open")

	def test_a_user_with_edit_rights_gets_no_share(self):
		checklist = _checklist({"description": "Call back", "assigned_to": EDITOR})
		self.assertTrue(checklist.checklist_items[0].todo)
		self.assertEqual(_shared_users(checklist), set())

	def test_a_share_made_by_hand_survives_the_assignment(self):
		checklist = _checklist({"description": "Call back"})
		frappe.share.add_docshare("Checklist", checklist.name, USER_A, read=1, write=1)

		checklist.checklist_items[0].assigned_to = USER_A
		checklist.save()
		checklist.checklist_items[0].assigned_to = None
		checklist.save()

		self.assertEqual(_shared_users(checklist), {USER_A})

	def test_an_assignee_with_only_a_share_cannot_assign_others(self):
		checklist = _checklist({"description": "Mine", "assigned_to": USER_C}, {"description": "Other"})
		other = checklist.checklist_items[1]

		frappe.set_user(USER_C)
		with self.assertRaises(frappe.ValidationError):
			checklist_inbox.update_spa_checklist_item(checklist.name, other.name, {"assigned_to": USER_A})

	def test_assignment_is_blocked_while_document_sharing_is_disabled(self):
		real = frappe.get_system_settings
		with patch(
			"frappe.get_system_settings",
			side_effect=lambda key: 1 if key == "disable_document_sharing" else real(key),
		):
			with self.assertRaises(frappe.ValidationError):
				_checklist({"description": "Call back", "assigned_to": USER_A})
			checklist = _checklist({"description": "Call back", "assigned_to": EDITOR})
		self.assertEqual(_shared_users(checklist), set())

	def test_assignee_can_close_their_todo_after_the_owner_left(self):
		_ensure_user(USER_B)
		checklist = frappe.get_doc(
			{
				"doctype": "Checklist",
				"title": "Owner leaves",
				"checklist_owner": USER_B,
				"checklist_items": [{"description": "Call back", "assigned_to": USER_A}],
			}
		).insert()
		frappe.db.set_value("User", USER_B, "enabled", 0)

		todo = _todo(checklist.checklist_items[0])
		todo.status = "Closed"
		todo.save()

		checklist.reload()
		self.assertEqual(checklist.checklist_items[0].done, 1)

	def test_todo_description_is_escaped_once(self):
		checklist = _checklist({"description": "Café & <i>tea</i>", "assigned_to": USER_A})
		description = _todo(checklist.checklist_items[0]).description
		self.assertIn("Café &amp; tea", description)
		self.assertNotIn("&amp;amp;", description)
