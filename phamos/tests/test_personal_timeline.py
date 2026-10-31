# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Day timeline data (#1573), with Employee-only users."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.api import personal_cockpit as pc
from phamos.api import personal_timeline as timeline
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "tl-a@example.com"
OTHER = "tl-b@example.com"
DAY = "2026-10-13"
NEXT = "2026-10-14"


class TestPersonalTimeline(FrappeTestCase):
	def setUp(self):
		patcher = patch("frappe.desk.form.assign_to.notify_assignment")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		for user in (USER, OTHER):
			_ensure_user(user)
		self.employee = _ensure_employee(USER)
		self.other_employee = _ensure_employee(OTHER)
		self.project = frappe.get_doc({"doctype": "Project", "project_name": "TL Timeline", "status": "Open"}).insert(
			ignore_permissions=True
		).name
		self.has_checkins = bool(frappe.db.exists("DocType", "Employee Checkin"))

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _checkin(self, log_type, time, employee=None):
		frappe.get_doc(
			{"doctype": "Employee Checkin", "employee": employee or self.employee, "log_type": log_type, "time": time}
		).insert(ignore_permissions=True)

	def _record(self, rows, employee=None, submit=False, goal="TL work"):
		doc = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": employee or self.employee,
				"project": self.project,
				"goal": goal,
				"expected_time": 3600,
				"from_time": rows[0][0],
				"item": [{"from_time": start, "to_time": end} for start, end in rows],
			}
		)
		doc.insert(ignore_permissions=True)
		if submit:
			doc.db_set("docstatus", 1)
		return doc.name

	def _closed_todo(self, text, closed_on, user=USER, important=0):
		todo = frappe.get_doc({"doctype": "ToDo", "allocated_to": user, "description": text}).insert(ignore_permissions=True)
		frappe.db.set_value(
			"ToDo",
			todo.name,
			{"status": "Closed", "cockpit_closed_on": closed_on, "cockpit_closed_by": user, "cockpit_important": important},
			update_modified=False,
		)
		return todo.name

	def _day(self, data, date):
		return next(day for day in data["days"] if day["date"] == getdate(date))

	def test_days_hold_my_checkins_todos_and_plan(self):
		if self.has_checkins:
			self._checkin("IN", f"{DAY} 08:00:00")
			self._checkin("OUT", f"{DAY} 17:00:00")
			self._checkin("IN", f"{DAY} 09:00:00", employee=self.other_employee)
		planned = self._closed_todo("Planned work", f"{DAY} 11:00:00", important=1)
		self._closed_todo("Their work", f"{DAY} 12:00:00", user=OTHER)
		frappe.get_doc(
			{
				"doctype": "Day Plan",
				"user": USER,
				"date": DAY,
				"status": "Closed",
				"confirmed_at": f"{DAY} 08:30:00",
				"frozen_at": f"{DAY} 08:30:00",
				"reflection": "Good day",
				"items": [{"todo": planned, "summary": "Planned work", "added_at": f"{DAY} 08:00:00", "outcome": "Done"}],
			}
		).insert(ignore_permissions=True)

		frappe.set_user(USER)
		data = pc.get_timeline(DAY, NEXT)
		self.assertEqual([str(day["date"]) for day in data["days"]], [DAY, NEXT])
		day = self._day(data, DAY)
		if self.has_checkins:
			self.assertEqual([c.log_type for c in day["checkins"]], ["IN", "OUT"])
		self.assertEqual(
			[(t["summary"], t["important"], t["planned"]) for t in day["todos_done"]], [("Planned work", True, True)]
		)
		self.assertEqual(day["plan"]["reflection"], "Good day")
		self.assertEqual(day["plan"]["counts"]["done"], 1)
		self.assertIsNone(self._day(data, NEXT)["plan"])

	def test_time_logs_carry_work_and_break_segments(self):
		self._record(
			[(f"{DAY} 09:00:00", f"{DAY} 10:00:00"), (f"{DAY} 10:00:00", f"{DAY} 10:15:00"), (f"{DAY} 10:15:00", f"{DAY} 11:00:00")],
			submit=True,
		)
		running = self._record([(f"{NEXT} 14:00:00", None)], goal="TL running")
		self._record([(f"{DAY} 09:00:00", f"{DAY} 10:00:00")], employee=self.other_employee, goal="TL theirs")
		frappe.set_user(USER)
		logs = pc.get_timeline(DAY, NEXT)["time_logs"]
		self.assertEqual([log["goal"] for log in logs], ["TL work", "TL running"])
		self.assertEqual([s["kind"] for s in logs[0]["segments"]], ["work", "break", "work"])
		self.assertEqual(logs[0]["project_name"], "TL Timeline")
		self.assertEqual(logs[1]["name"], running)
		self.assertIsNone(logs[1]["segments"][0]["to_time"])

	def test_a_record_from_the_day_before_reaching_into_the_range(self):
		self._record([("2026-10-12 23:00:00", f"{DAY} 01:00:00")], submit=True, goal="TL overnight")
		self._record([("2026-10-12 08:00:00", "2026-10-12 09:00:00")], submit=True, goal="TL before")
		frappe.set_user(USER)
		self.assertEqual([log["goal"] for log in pc.get_timeline(DAY, DAY)["time_logs"]], ["TL overnight"])

	def test_has_earlier(self):
		frappe.set_user(USER)
		self.assertFalse(pc.get_timeline(DAY, NEXT)["has_earlier"])
		self._closed_todo("Long ago", "2026-09-01 10:00:00")
		self.assertTrue(pc.get_timeline(DAY, NEXT)["has_earlier"])

	def test_range_limits(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.ValidationError):
			pc.get_timeline(NEXT, DAY)
		with self.assertRaises(frappe.ValidationError):
			pc.get_timeline("2026-09-01", "2026-10-15")
		self.assertEqual(len(pc.get_timeline("2026-10-01", "2026-10-31")["days"]), 31)

	def test_without_hrms_or_employee(self):
		original = frappe.db.exists

		def exists(doctype, *args, **kwargs):
			if doctype == "DocType" and args and args[0] == "Employee Checkin":
				return None
			return original(doctype, *args, **kwargs)

		frappe.set_user(USER)
		with patch.object(timeline.frappe.db, "exists", side_effect=exists):
			data = pc.get_timeline(DAY, DAY)
		self.assertEqual(data["days"][0]["checkins"], [])

		frappe.set_user("Administrator")
		frappe.db.set_value("Employee", self.employee, "status", "Inactive")
		frappe.set_user(USER)
		data = pc.get_timeline(DAY, DAY)
		self.assertIsNone(data["employee"])
		self.assertEqual(data["time_logs"], [])
