# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Day (#1559). "Today" is pinned to Wednesday 2026-10-14; users have no Employee record."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime, getdate

from phamos.api import personal_cockpit as pc
from phamos.api import personal_day_plan as day_plan
from phamos.api import personal_todos

USER = "dp-a@example.com"
OTHER = "dp-b@example.com"
TODAY = "2026-10-14"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


class TestMyDay(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		self.now = get_datetime(f"{TODAY} 08:30:00")
		for target, value in (
			(day_plan, "today"),
			(personal_todos, "today"),
		):
			p = patch.object(target, value, return_value=TODAY)
			p.start()
			self.addCleanup(p.stop)
		clock = patch.object(day_plan, "now_datetime", side_effect=lambda: self.now)
		clock.start()
		self.addCleanup(clock.stop)
		no_employee = patch("phamos.cockpits.workdays._employee", return_value=None)
		no_employee.start()
		self.addCleanup(no_employee.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _todo(self, description, date=None, user=USER, important=0, estimate=None):
		doc = frappe.get_doc(
			{"doctype": "ToDo", "allocated_to": user, "description": description, "date": date}
		).insert(ignore_permissions=True)
		doc.db_set({"cockpit_important": important, "cockpit_estimate_minutes": estimate or 0})
		return doc

	def _item(self, plan, name):
		return next(i for i in plan["items"] if i["todo"] == name)

	def _group(self, plan, key):
		return [t["summary"] for t in next(g for g in plan["candidates"] if g["key"] == key)["items"]]

	def test_candidates_are_grouped(self):
		self._todo("Overdue", "2026-10-10")
		self._todo("Today", TODAY)
		self._todo("Important someday", important=1)
		self._todo("Friday", "2026-10-16")
		self._todo("Next month", "2026-11-20")
		frappe.set_user(USER)
		plan = pc.get_day_plan()
		self.assertEqual(self._group(plan, "overdue"), ["Overdue"])
		self.assertEqual(self._group(plan, "due_today"), ["Today"])
		self.assertEqual(self._group(plan, "important"), ["Important someday"])
		self.assertEqual(self._group(plan, "this_week"), ["Friday"])
		self.assertFalse(plan["exists"])

	def test_add_remove_and_reorder(self):
		first = self._todo("First", estimate=60)
		second = self._todo("Second")
		frappe.set_user(USER)
		pc.add_to_day(first.name)
		plan = pc.add_to_day(second.name)
		self.assertEqual([i["todo"] for i in plan["items"]], [first.name, second.name])
		self.assertEqual(plan["remaining_minutes"], 60 + day_plan.DEFAULT_ESTIMATE_MINUTES)
		self.assertEqual(plan["unestimated"], 1)
		plan = pc.move_in_day(second.name, "up")
		self.assertEqual([i["todo"] for i in plan["items"]], [second.name, first.name])
		plan = pc.remove_from_day(second.name)
		self.assertEqual([i["todo"] for i in plan["items"]], [first.name])

	def test_only_my_open_todos(self):
		theirs = self._todo("Theirs", user=OTHER)
		closed = self._todo("Closed")
		closed.db_set("status", "Closed")
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			pc.add_to_day(theirs.name)
		with self.assertRaises(frappe.ValidationError):
			pc.add_to_day(closed.name)
		with self.assertRaises(frappe.ValidationError):
			pc.add_to_day(self._todo("Past").name, "2026-10-13")

	def test_start_fixes_the_plan_and_later_adds_are_spontaneous(self):
		planned = self._todo("Planned")
		later = self._todo("Later")
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.start_day()
		pc.add_to_day(planned.name)
		plan = pc.start_day()
		self.assertEqual(plan["status"], "Confirmed")
		self.now += timedelta(hours=2)
		plan = pc.add_to_day(later.name)
		self.assertTrue(self._item(plan, planned.name)["planned"])
		self.assertFalse(self._item(plan, later.name)["planned"])

	def test_freeze_fixes_unstarted_plans(self):
		todo = self._todo("Draft only")
		frappe.set_user(USER)
		pc.add_to_day(todo.name)
		frappe.set_user("Administrator")
		self.now += timedelta(hours=2)
		with patch("frappe.db.commit"):
			day_plan.freeze_day_plans()
		frappe.set_user(USER)
		plan = pc.get_day_plan()
		self.assertTrue(plan["auto_fixed"])
		self.assertTrue(self._item(plan, todo.name)["planned"])

	def test_closed_todo_shows_as_done(self):
		todo = self._todo("Close me")
		frappe.set_user(USER)
		pc.add_to_day(todo.name)
		pc.close_todo(todo.name)
		self.assertEqual(self._item(pc.get_day_plan(), todo.name)["outcome"], "Done")
		self.assertEqual(pc.get_day_state(), {"status": "Draft", "planned": 1, "done": 1})

	def test_shutdown_needs_a_decision_for_every_open_item(self):
		todos = {key: self._todo(key) for key in ("tomorrow", "week", "drop", "keep", "done")}
		frappe.set_user(USER)
		for todo in todos.values():
			pc.add_to_day(todo.name)
		pc.start_day()
		pc.close_todo(todos["done"].name)
		with self.assertRaises(frappe.ValidationError):
			pc.shutdown_day([{"todo": todos["tomorrow"].name, "action": "tomorrow"}])
		plan = pc.shutdown_day(
			[
				{"todo": todos["tomorrow"].name, "action": "tomorrow"},
				{"todo": todos["week"].name, "action": "later_this_week"},
				{"todo": todos["drop"].name, "action": "drop", "reason": "Out of date"},
				{"todo": todos["keep"].name, "action": "keep"},
			],
			reflection="Good day",
		)
		self.assertEqual(plan["status"], "Closed")
		self.assertEqual(plan["reflection"], "Good day")
		outcomes = {i["todo"]: i["outcome"] for i in plan["items"]}
		self.assertEqual(outcomes[todos["done"].name], "Done")
		self.assertEqual(outcomes[todos["drop"].name], "Dropped")
		self.assertEqual(outcomes[todos["keep"].name], "Open")
		self.assertEqual(outcomes[todos["week"].name], "Moved")
		self.assertEqual(getdate(frappe.db.get_value("ToDo", todos["week"].name, "date")), getdate("2026-10-16"))
		self.assertEqual(frappe.db.get_value("ToDo", todos["drop"].name, "status"), "Cancelled")

		# Tomorrow's plan already holds the moved ToDo, carried over once.
		tomorrow = pc.get_day_plan("2026-10-15")
		item = self._item(tomorrow, todos["tomorrow"].name)
		self.assertEqual((item["carried_over"], item["rollover_count"]), (True, 1))
		self.assertEqual(getdate(frappe.db.get_value("ToDo", todos["tomorrow"].name, "date")), getdate("2026-10-15"))
		# The one kept open comes back as a leftover, not silently.
		self.assertEqual(self._group(tomorrow, "leftovers"), ["keep"])
		with self.assertRaises(frappe.ValidationError):
			pc.add_to_day(self._todo("Late").name)

	def test_unshut_day_leaves_leftovers_with_a_counter(self):
		todo = self._todo("Lingering")
		frappe.get_doc(
			{
				"doctype": "Day Plan",
				"user": USER,
				"date": "2026-10-13",
				"status": "Confirmed",
				"items": [{"todo": todo.name, "summary": "Lingering", "rollover_count": 2, "outcome": "Open"}],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)
		leftovers = next(g for g in pc.get_day_plan()["candidates"] if g["key"] == "leftovers")["items"]
		self.assertEqual([(t["summary"], t["rollover_count"]) for t in leftovers], [("Lingering", 3)])
		plan = pc.add_to_day(todo.name)
		self.assertEqual(self._item(plan, todo.name)["rollover_count"], 3)

	def test_calibration_needs_enough_samples(self):
		for index in range(5):
			todo = self._todo(f"Done {index}")
			todo.db_set(
				{
					"status": "Closed",
					"cockpit_closed_on": f"{TODAY} 09:00:00",
					"cockpit_estimate_minutes": 30,
					"cockpit_actual_minutes": 42,
				}
			)
		frappe.set_user(USER)
		self.assertEqual(day_plan.calibration(), {"samples": 5, "factor": 1.4})

	def test_plans_are_private(self):
		todo = self._todo("Mine")
		frappe.set_user(USER)
		pc.add_to_day(todo.name)
		frappe.set_user(OTHER)
		self.assertEqual(frappe.get_list("Day Plan", pluck="name"), [])
		self.assertFalse(pc.get_day_plan()["exists"])

	def test_deleting_a_planned_todo(self):
		todo = self._todo("Goes away")
		frappe.set_user(USER)
		pc.add_to_day(todo.name)
		frappe.set_user("Administrator")
		frappe.delete_doc("ToDo", todo.name)
		frappe.set_user(USER)
		self.assertEqual(pc.get_day_plan()["items"], [])

	def test_a_day_starts_only_on_the_day_itself(self):
		todo = self._todo("Tomorrow's work")
		frappe.set_user(USER)
		pc.add_to_day(todo.name, "2026-10-15")
		with self.assertRaises(frappe.ValidationError):
			pc.start_day("2026-10-15")
