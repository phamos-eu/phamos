# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issues and Tasks dashboards of the Personal Cockpit (#1604): only my assignments count."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, now_datetime, today

from phamos.api import personal_cockpit as pc
from phamos.api import personal_work_dashboard as wd
from phamos.tests.test_personal_checkin import _ensure_employee
from phamos.tests.test_personal_cockpit import _ensure_user

USER = "wd-a@example.com"
OTHER = "wd-b@example.com"


def _assign(doctype, name, user, status="Open"):
	"""An assignment ToDo, inserted directly so no notification e-mail commits the test."""
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"reference_type": doctype,
			"reference_name": name,
			"description": name,
			"status": status,
		}
	).insert(ignore_permissions=True)


class TestPersonalWorkDashboard(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for user in (USER, OTHER):
			_ensure_user(user)
		self.day = getdate(today())

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _issue(self, subject, status="Open", opened_days_ago=0, user=USER, assignment="Open"):
		doc = frappe.get_doc({"doctype": "Issue", "subject": subject}).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Issue", doc.name, {"status": status, "opening_date": add_days(self.day, -opened_days_ago)}
		)
		_assign("Issue", doc.name, user, assignment)
		return doc.name

	def _task(self, subject, user=USER, assignment="Open", **values):
		doc = frappe.get_doc({"doctype": "Task", "subject": subject}).insert(ignore_permissions=True)
		if values:
			frappe.db.set_value("Task", doc.name, values)
		_assign("Task", doc.name, user, assignment)
		return doc.name

	def test_issue_numbers_cover_my_assignments_only(self):
		self._issue("WD waits on me", "Open", opened_days_ago=40)
		self._issue("WD waits on the customer", "Replied", opened_days_ago=3)
		self._issue("WD on hold", "On Hold")
		self._issue("WD resolved", "Resolved", assignment="Closed")
		self._issue("WD someone else's", "Open", opened_days_ago=200, user=OTHER)
		frappe.set_user(USER)
		data = pc.get_issue_dashboard()
		totals = data["totals"]
		self.assertEqual(
			(totals["open"], totals["waiting_on_me"], totals["waiting_on_others"], totals["resolved_recently"]),
			(3, 1, 2, 1),
		)
		self.assertEqual(totals["oldest_days"], 40)
		self.assertEqual(data["oldest"][0]["age_days"], 40)
		self.assertEqual({row["label"]: row["value"] for row in data["by_status"]}, {"Open": 1, "Replied": 1, "On Hold": 1})
		self.assertEqual(sum(row["value"] for row in data["by_age"]), 3)
		self.assertEqual(dict((row["label"], row["value"]) for row in data["by_age"])["31–90 days"], 1)

	def test_without_assignments_everything_is_zero(self):
		frappe.set_user(USER)
		issues = pc.get_issue_dashboard()
		self.assertEqual(issues["totals"]["open"], 0)
		self.assertIsNone(issues["totals"]["oldest_days"])
		tasks = pc.get_task_dashboard()
		self.assertEqual(tasks["totals"], {"open": 0, "overdue": 0, "due_soon": 0, "completed_recently": 0})
		self.assertEqual((tasks["next_due"], tasks["effort"]), ([], []))

	def test_task_numbers_and_effort(self):
		overdue = self._task("WD overdue", exp_end_date=add_days(self.day, -2), expected_time=4, actual_time=6)
		self._task("WD due soon", exp_end_date=add_days(self.day, 3), expected_time=8, actual_time=2)
		self._task("WD later", exp_end_date=add_days(self.day, 30))
		self._task("WD done", assignment="Closed", status="Completed", completed_on=add_days(self.day, -1))
		self._task("WD done long ago", assignment="Closed", status="Completed", completed_on=add_days(self.day, -40))
		self._task("WD someone else's", user=OTHER, exp_end_date=add_days(self.day, -5))
		frappe.set_user(USER)
		data = pc.get_task_dashboard()
		self.assertEqual(data["totals"], {"open": 3, "overdue": 1, "due_soon": 1, "completed_recently": 1})
		self.assertEqual([row["name"] for row in data["next_due"]][0], overdue)
		self.assertTrue(data["next_due"][0]["overdue"])
		self.assertEqual([(row["label"], row["value"], row["theme"]) for row in data["effort"]], [
			("WD overdue", 150, "red"),
			("WD due soon", 25, "blue"),
		])

	def test_my_hours_from_submitted_records(self):
		employee = _ensure_employee(USER)
		project = frappe.db.get_value("Project", {"status": "Open"}, "name")
		if not project:
			self.skipTest("needs an open Project")

		def record(start, seconds, docstatus=1):
			doc = frappe.get_doc(
				{
					"doctype": "Timesheet Record",
					"employee": employee,
					"project": project,
					"goal": "WD hours",
					"expected_time": 3600,
					"from_time": start,
				}
			).insert(ignore_permissions=True)
			frappe.db.set_value("Timesheet Record", doc.name, {"docstatus": docstatus, "actual_time": seconds})

		now = now_datetime()
		record(now - timedelta(minutes=90), 3600)  # today
		record(now - timedelta(minutes=30), 1800, docstatus=0)  # a running draft does not count
		record(now - timedelta(days=60), 7200)  # outside week and month
		frappe.set_user(USER)
		with patch.object(wd, "get_first_day_of_week", return_value=self.day), patch.object(
			wd, "get_first_day", return_value=self.day
		):
			hours = pc.get_task_dashboard()["hours"]
		self.assertEqual(hours, {"today": 1.0, "week": 1.0, "month": 1.0})

	def test_no_employee_means_no_hours(self):
		frappe.set_user(OTHER)
		self.assertIsNone(pc.get_task_dashboard()["hours"])

	def test_statuses_outside_the_order_still_show(self):
		rows = [{"status": "Open"}, {"status": "Waiting for Customer"}, {"status": "Waiting for Customer"}, {"status": None}]
		self.assertEqual(
			wd._count_by(rows, "status", order=["Open", "Replied"]),
			[
				{"label": "Open", "value": 1},
				{"label": "Waiting for Customer", "value": 2},
				{"label": "—", "value": 1},
			],
		)

	def test_only_the_cockpit_wrappers_are_endpoints(self):
		self.assertIn(pc.get_issue_dashboard, frappe.whitelisted)
		self.assertIn(pc.get_task_dashboard, frappe.whitelisted)
		self.assertNotIn(wd.get_issue_dashboard, frappe.whitelisted)
		self.assertNotIn(wd.get_task_dashboard, frappe.whitelisted)

	def test_due_soon_is_today_and_the_next_six_days(self):
		self._task("WD due today", exp_end_date=self.day)
		self._task("WD due on day seven", exp_end_date=add_days(self.day, wd.DUE_SOON_DAYS - 1))
		self._task("WD due on day eight", exp_end_date=add_days(self.day, wd.DUE_SOON_DAYS))
		frappe.set_user(USER)
		self.assertEqual(pc.get_task_dashboard()["totals"]["due_soon"], 2)
