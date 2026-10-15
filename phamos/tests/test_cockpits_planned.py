# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Planned vs spontaneous closures (#1561)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, getdate, now_datetime, today

from phamos.api import personal_challenges as challenges
from phamos.api import personal_cockpit as pc

USER = "ps-a@example.com"
DAY = "2026-10-13"  # a Tuesday


def _ensure_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	if "Employee" not in frappe.get_roles(email):
		frappe.get_doc("User", email).add_roles("Employee")


class TestPlannedVsSpontaneous(FrappeTestCase):
	def setUp(self):
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		no_employee = patch("phamos.cockpits.workdays._employee", return_value=None)
		no_employee.start()
		self.addCleanup(no_employee.stop)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _closed(self, label, closed_at, created_at=None):
		todo = frappe.get_doc({"doctype": "ToDo", "allocated_to": USER, "description": label}).insert(
			ignore_permissions=True
		)
		frappe.db.set_value(
			"ToDo",
			todo.name,
			{
				"status": "Closed",
				"cockpit_closed_on": closed_at,
				"cockpit_closed_by": USER,
				"creation": created_at or add_to_date(closed_at, hours=-3),
			},
			update_modified=False,
		)
		return todo.name

	def _plan(self, day, items, fixed_at=None):
		return frappe.get_doc(
			{
				"doctype": "Day Plan",
				"user": USER,
				"date": day,
				"status": "Confirmed" if fixed_at else "Draft",
				"confirmed_at": fixed_at,
				"frozen_at": fixed_at,
				"items": [{"todo": name, "summary": name, "added_at": added, "outcome": "Open"} for name, added in items],
			}
		).insert(ignore_permissions=True)

	def test_split_counts_planned_spontaneous_and_caps_quick_wins(self):
		planned = self._closed("Planned", f"{DAY} 12:00:00")
		added_later = self._closed("Added after the start", f"{DAY} 15:00:00")
		self._closed("Not on the plan", f"{DAY} 16:00:00")
		for index in range(3):
			self._closed(f"Quick {index}", f"{DAY} 17:0{index}:00", created_at=f"{DAY} 17:00:00")
		self._plan(DAY, [(planned, f"{DAY} 08:30:00"), (added_later, f"{DAY} 11:00:00")], fixed_at=f"{DAY} 09:00:00")
		self.assertEqual(
			challenges.split_by_day(USER, DAY, DAY), {getdate(DAY): {"planned": 1, "spontaneous": 4}}
		)

	def test_unfixed_plan_counts_all_items_as_planned(self):
		first = self._closed("First", f"{DAY} 12:00:00")
		second = self._closed("Second", f"{DAY} 13:00:00")
		self._plan(DAY, [(first, f"{DAY} 08:00:00"), (second, f"{DAY} 12:30:00")])
		self.assertEqual(challenges.split_by_day(USER, DAY, DAY)[getdate(DAY)], {"planned": 2, "spontaneous": 0})

	def test_split_challenge_needs_both_targets(self):
		planned = self._closed("Planned", f"{DAY} 12:00:00")
		self._closed("Spontaneous", f"{DAY} 14:00:00")
		self._plan(DAY, [(planned, f"{DAY} 08:00:00")], fixed_at=f"{DAY} 09:00:00")
		self._closed("Only spontaneous", "2026-10-12 14:00:00")
		frappe.set_user(USER)
		with patch.object(challenges, "today", return_value="2026-10-12"):
			created = pc.create_challenge(
				"Planned and spontaneous", working_days=5, start_date="2026-10-12", target_planned=1, target_spontaneous=1
			)
		self.assertEqual(created["title"], "1 planned + 1 spontaneous a day for 5 working days")
		self.assertEqual(created["target_per_day"], 2)
		with patch.object(challenges, "today", return_value="2026-10-14"):
			data = pc.get_challenges()["active"][0]
		results = {str(d["date"]): d["result"] for d in data["days"]}
		self.assertEqual(results["2026-10-12"], "Joker")  # spontaneous only: not met
		self.assertEqual(results["2026-10-13"], "Met")
		day = next(d for d in data["days"] if str(d["date"]) == DAY)
		self.assertEqual((day["planned"], day["spontaneous"]), (1, 1))
		self.assertTrue(data["split"])

	def test_split_challenge_validation(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.create_challenge("Planned and spontaneous", working_days=5, target_planned=0, target_spontaneous=0)

	def test_dashboard_shows_the_split(self):
		now = now_datetime()
		planned = self._closed("Planned today", add_to_date(now, minutes=-30))
		self._closed("Spontaneous today", add_to_date(now, minutes=-20))
		self._plan(today(), [(planned, add_to_date(now, hours=-5))], fixed_at=add_to_date(now, hours=-4))
		frappe.set_user(USER)
		data = pc.get_todo_dashboard(7)
		self.assertEqual((data["closures"]["planned"], data["closures"]["spontaneous"]), (1, 1))
		flags = {t["summary"]: t["planned"] for t in data["today"]["done"]}
		self.assertEqual(flags, {"Planned today": True, "Spontaneous today": False})
