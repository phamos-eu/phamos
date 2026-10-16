# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Timesheet timer of the Personal Cockpit (#1572), with Employee-only users.

The Developer Action Panel functions underneath commit; commits are patched out so every
test rolls back.
"""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from phamos.api import personal_cockpit as pc
from phamos.api import personal_timer as timer
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "tm-a@example.com"
OTHER = "tm-b@example.com"
NO_EMPLOYEE = "tm-c@example.com"
DAP = "phamos.phamos.page.dev_action_panel.dev_action_panel"


class TestPersonalTimer(FrappeTestCase):
	def setUp(self):
		for target in ("frappe.db.commit", "frappe.desk.form.assign_to.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		for user in (USER, OTHER, NO_EMPLOYEE):
			_ensure_user(user)
		self.employee = _ensure_employee(USER)
		self.other_employee = _ensure_employee(OTHER)
		frappe.db.set_value("Employee", self.employee, "activity_type", self._activity_type())
		self.project = self._project("TM Timer project")
		self.other_project = self._project("TM Other project")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _activity_type(self):
		name = "TM Development"
		if not frappe.db.exists("Activity Type", name):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(ignore_permissions=True)
		return name

	def _project(self, project_name, task_rule="Task is optional"):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": project_name,
					"status": "Open",
					"task_in_timesheet_record": task_rule,
					"percent_billable": "75",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _task(self, project, subject="TM task"):
		return frappe.get_doc({"doctype": "Task", "subject": subject, "project": project}).insert(ignore_permissions=True).name

	def _start(self, user=USER, **kwargs):
		frappe.set_user(user)
		args = {"project": self.project, "expected_seconds": 3600, "goal": "Write the report"}
		args.update(kwargs)
		return pc.start_timer(**args)

	def test_no_employee_means_no_timer(self):
		frappe.set_user(NO_EMPLOYEE)
		state = pc.get_timer_state()
		self.assertEqual((state["available"], state["can_start"]), (False, False))
		with self.assertRaises(frappe.ValidationError):
			pc.start_timer(self.project, 3600, "Goal")

	def test_start_creates_the_running_record_like_the_panels(self):
		task = self._task(self.project)
		state = self._start(task=task)
		session = state["session"]
		self.assertEqual((session["state"], session["kind"], session["task"]), ("running", "project", task))
		doc = frappe.get_doc("Timesheet Record", session["name"])
		self.assertEqual((doc.employee, doc.project, doc.goal, doc.expected_time), (self.employee, self.project, "Write the report", 3600))
		self.assertEqual(doc.activity_type, "TM Development")
		self.assertEqual(len(doc.item), 1)
		self.assertFalse(doc.item[0].to_time)
		self.assertFalse(state["can_start"])
		self.assertEqual(session["project_percent_billable"], "75")

	def test_task_rules(self):
		mandatory = self._project("TM Mandatory", task_rule="Task is mandatory")
		with self.assertRaises(frappe.ValidationError):
			self._start(project=mandatory)
		with self.assertRaises(frappe.ValidationError):
			self._start(task=self._task(self.other_project))
		hidden = self._project("TM Hidden", task_rule="Task is hidden")
		state = self._start(project=hidden, task=self._task(hidden))
		self.assertIsNone(state["session"]["task"])

	def test_validation_of_goal_and_expected_time(self):
		with self.assertRaises(frappe.ValidationError):
			self._start(goal="  ")
		with self.assertRaises(frappe.ValidationError):
			self._start(expected_seconds=600)

	def test_a_running_timer_blocks_a_second_start(self):
		self._start()
		with self.assertRaises(frappe.ValidationError):
			self._start(project=self.other_project)

	def test_pause_and_resume(self):
		name = self._start()["session"]["name"]
		paused = pc.pause_timer(name)["session"]
		self.assertEqual(paused["state"], "paused")
		self.assertTrue(paused["break_from"])
		self.assertEqual(pc.resume_timer(name)["session"]["state"], "running")
		self.assertEqual(len(frappe.get_doc("Timesheet Record", name).item), 3)

	def test_resume_can_log_the_break(self):
		name = self._start()["session"]["name"]
		pc.pause_timer(name)
		pc.resume_timer(
			name,
			break_project=self.other_project,
			break_goal="Customer call",
			break_result="Agreed on the scope",
			break_activity_type="TM Development",
		)
		breaks = frappe.get_all(
			"Timesheet Record",
			filters={"employee": self.employee, "project": self.other_project, "docstatus": 1},
			fields=["goal", "result", "percent_billable"],
		)
		self.assertEqual([(b.goal, b.result, b.percent_billable) for b in breaks], [("Customer call", "Agreed on the scope", "0")])

	def test_stop_submits_and_creates_the_erpnext_timesheet(self):
		name = self._start()["session"]["name"]
		start = frappe.db.get_value("Timesheet Record", name, "from_time")
		frappe.db.set_value("Timesheet Record Item", {"parent": name}, "from_time", add_to_date(start, minutes=-30))
		frappe.db.set_value("Timesheet Record", name, "from_time", add_to_date(start, minutes=-30))
		result = pc.stop_timer(name, "Report written", percent_billable="50", activity_type="TM Development")
		self.assertEqual(result["outcome"]["session_state"], "submitted")
		self.assertIsNone(result["state"]["session"])
		doc = frappe.get_doc("Timesheet Record", name)
		self.assertEqual((doc.docstatus, doc.result, doc.percent_billable), (1, "Report written", "50"))
		self.assertTrue(doc.timesheet)
		self.assertEqual(frappe.db.get_value("Timesheet", doc.timesheet, "employee"), self.employee)

	def test_stop_needs_result_and_activity_type(self):
		name = self._start()["session"]["name"]
		with self.assertRaises(frappe.ValidationError):
			pc.stop_timer(name, " ", activity_type="TM Development")
		with self.assertRaises(frappe.ValidationError):
			pc.stop_timer(name, "Done", activity_type=None)
		with self.assertRaises(frappe.ValidationError):
			pc.stop_timer(name, "Done", percent_billable="33", activity_type="TM Development")
		with self.assertRaises(frappe.ValidationError):
			pc.stop_timer(name, "Done", activity_type="TM Development", manual_end_time=str(now_datetime() - timedelta(days=1)))

	def test_someone_elses_record_cannot_be_touched(self):
		name = self._start(user=OTHER)["session"]["name"]
		frappe.set_user(USER)
		for call in (
			lambda: pc.pause_timer(name),
			lambda: pc.resume_timer(name),
			lambda: pc.stop_timer(name, "Hijacked", activity_type="TM Development"),
			lambda: pc.continue_timer_with_available_hours(name),
			lambda: pc.notify_timer_account_manager(name),
			lambda: pc.discard_timer_draft(name),
		):
			with self.assertRaises(frappe.PermissionError):
				call()
		self.assertEqual(len(frappe.get_doc("Timesheet Record", name).item), 1)

	def test_empty_drafts_block_and_can_be_discarded(self):
		draft = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": self.employee,
				"project": self.project,
				"goal": "Old draft",
				"expected_time": 3600,
				"from_time": now_datetime(),
			}
		).insert(ignore_permissions=True)
		frappe.set_user(USER)
		state = pc.get_timer_state()
		self.assertFalse(state["can_start"])
		self.assertEqual([d["name"] for d in state["blocking_drafts"]], [draft.name])
		self.assertTrue(pc.discard_timer_draft(draft.name)["can_start"])
		self.assertFalse(frappe.db.exists("Timesheet Record", draft.name))

	def test_drafts_with_time_are_not_discarded(self):
		name = self._start()["session"]["name"]
		with self.assertRaises(frappe.ValidationError):
			pc.discard_timer_draft(name)

	def test_time_limit_exceeded_waits_for_a_decision(self):
		name = self._start()["session"]["name"]
		exceeds = {"exceeds": True, "remaining_hours": 0.5, "requested_hours": 1.0, "limit_hours": 10}
		with patch(f"{DAP}.compute_time_limit_status", return_value=dict(exceeds)), patch.object(
			timer, "compute_time_limit_status", return_value=dict(exceeds)
		):
			result = pc.stop_timer(name, "Report written", activity_type="TM Development")
			self.assertTrue(result["outcome"]["exceeds"])
			session = result["state"]["session"]
			self.assertEqual(session["state"], "limit_exceeded")
			self.assertEqual(session["limit"]["remaining_hours"], 0.5)
		with patch.object(timer, "submit_at_available_hours") as submit:
			pc.continue_timer_with_available_hours(name)
		submit.assert_called_once_with(name)

	def test_options_list_my_and_recent_projects(self):
		frappe.get_doc(
			{"doctype": "ToDo", "allocated_to": USER, "reference_type": "Project", "reference_name": self.other_project, "description": "Assigned"}
		).insert(ignore_permissions=True)
		name = self._start()["session"]["name"]
		pc.stop_timer(name, "Done", activity_type="TM Development")
		options = pc.get_timer_options()
		self.assertIn(self.other_project, [p.name for p in options["my_projects"]])
		self.assertEqual([p.name for p in options["recent_projects"]], [self.project])
		self.assertEqual(options["default_activity_type"], "TM Development")
		self.assertIn(self.project, [p.name for p in pc.search_timer_projects("TM Timer")])
		info = pc.get_timer_project_info(self.project)
		self.assertEqual((info["task_rule"], info["percent_billable"]), ("Task is optional", "75"))

	def test_changes_are_published_to_the_employees_user(self):
		with patch("frappe.publish_realtime") as publish:
			self._start()
		users = {c.kwargs.get("user") for c in publish.call_args_list if c.args[0] == "cockpit_timer_changed"}
		self.assertEqual(users, {USER})
