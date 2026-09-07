# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Regression guards: Timesheet Record creation via DAP and PAP.

These tests lock the create paths used by Developer Action Panel and
Project Action Panel so cockpit work does not break desk timer flows.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from phamos.phamos.page.dev_action_panel import dev_action_panel as dap
from phamos.phamos.page.project_action_panel import project_action_panel as pap
from phamos.phamos.timesheet_utils import normalize_percent_billable


class _FakeTimesheetRecord:
	"""Minimal stand-in for frappe.new_doc('Timesheet Record')."""

	def __init__(self):
		self.name = "TR-TEST-00001"
		self.doctype = "Timesheet Record"
		self.item = []
		self.project = None
		self.customer = None
		self.employee = None
		self.activity_type = None
		self.task = None
		self.goal = None
		self.expected_time = None
		self.from_time = None
		self.to_time = None
		self.result = None
		self.percent_billable = None
		self.actual_time = None
		self.status = None
		self.gitlab_issue = None
		self.gitlab_parent_issue = None
		self._saved = False
		self._inserted = False
		self._submitted = False

	def append(self, fieldname, values):
		row = SimpleNamespace(**values, idx=len(self.item) + 1)
		getattr(self, fieldname).append(row)
		return row

	def save(self, *args, **kwargs):
		self._saved = True
		return self

	def insert(self, *args, **kwargs):
		self._inserted = True
		return self

	def submit(self):
		self._submitted = True
		return self


class TestNormalizePercentBillableForActionPanels(FrappeTestCase):
	"""PAP submits percent_billable through the shared helper — keep Select-safe."""

	def test_zero_and_empty_become_zero(self):
		self.assertEqual(normalize_percent_billable(0), "0")
		self.assertEqual(normalize_percent_billable(None), "0")
		self.assertEqual(normalize_percent_billable(""), "0")

	def test_allowed_select_values_pass_through(self):
		for value in ("25", "50", "75", "100"):
			self.assertEqual(normalize_percent_billable(value), value)


class TestPapCreateTimesheetRecord(FrappeTestCase):
	"""Project Action Panel: create_timesheet_record."""

	def test_creates_draft_timesheet_record_with_required_fields(self):
		fake = _FakeTimesheetRecord()
		from_time = now_datetime()

		def get_value(doctype, filters, fieldname=None, **kwargs):
			if doctype == "Employee" and fieldname == "name":
				return "EMP-001"
			if doctype == "Employee" and fieldname == "activity_type":
				return "Development"
			if doctype == "Customer":
				return "CUST-001"
			if doctype == "Project":
				return "PROJ-001"
			return None

		with (
			patch("phamos.phamos.page.project_action_panel.project_action_panel.frappe.db.get_value", side_effect=get_value),
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel.frappe.new_doc",
				return_value=fake,
			) as new_doc,
			patch("phamos.phamos.page.project_action_panel.project_action_panel.frappe.db.commit"),
		):
			result = pap.create_timesheet_record(
				project_name="Demo Project",
				customer="Demo Customer",
				from_time=from_time,
				expected_time=3600,
				goal="Implement feature",
				task="TASK-001",
			)

		new_doc.assert_called_once_with("Timesheet Record")
		self.assertIs(result, fake)
		self.assertTrue(fake._saved)
		self.assertEqual(fake.project, "PROJ-001")
		self.assertEqual(fake.customer, "CUST-001")
		self.assertEqual(fake.employee, "EMP-001")
		self.assertEqual(fake.activity_type, "Development")
		self.assertEqual(fake.task, "TASK-001")
		self.assertEqual(fake.goal, "Implement feature")
		self.assertEqual(fake.expected_time, 3600)
		self.assertEqual(len(fake.item), 1)
		self.assertEqual(fake.item[0].from_time, from_time)

	def test_returns_none_when_employee_missing(self):
		# PAP wraps failures in try/except and returns None (desk shows no doc).
		with (
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel.frappe.db.get_value",
				return_value=None,
			),
			patch("phamos.phamos.page.project_action_panel.project_action_panel.frappe.log_error"),
		):
			result = pap.create_timesheet_record(
				project_name="Demo Project",
				customer="Demo Customer",
				from_time=now_datetime(),
				expected_time=3600,
				goal="No employee",
			)
		self.assertIsNone(result)


class TestPapCreateAndSubmitTimesheet(FrappeTestCase):
	"""Project Action Panel: create_and_submit_timesheet."""

	def test_creates_and_submits_timesheet_record(self):
		fake = _FakeTimesheetRecord()
		from_time = "2026-09-07 10:00:00"
		to_time = "2026-09-07 11:00:00"

		with (
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel.frappe.db.get_value",
				return_value="EMP-001",
			),
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel._find_gitlab_issues_in_text",
				return_value=(None, None),
			),
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel.frappe.new_doc",
				return_value=fake,
			) as new_doc,
		):
			result = pap.create_and_submit_timesheet(
				project_name="PROJ-001",
				goal="Ship fix",
				from_time=from_time,
				to_time=to_time,
				expected_time=3600,
				percent_billable=100,
				activity_type="Development",
				result="Done",
			)

		new_doc.assert_called_once_with("Timesheet Record")
		self.assertEqual(result["status"], "success")
		self.assertEqual(result["name"], fake.name)
		self.assertTrue(fake._inserted)
		self.assertTrue(fake._submitted)
		self.assertEqual(fake.project, "PROJ-001")
		self.assertEqual(fake.employee, "EMP-001")
		self.assertEqual(fake.percent_billable, "100")
		self.assertEqual(fake.status, "Complete")
		self.assertEqual(len(fake.item), 1)
		self.assertEqual(fake.item[0].from_time, from_time)
		self.assertEqual(fake.item[0].to_time, to_time)


class TestDapStartProjectTimer(FrappeTestCase):
	"""Developer Action Panel: start_project_timer (project-based create)."""

	def test_creates_running_draft_timesheet_record(self):
		fake = _FakeTimesheetRecord()
		employee = SimpleNamespace(name="EMP-001", activity_type="Development")

		with (
			patch(
				"phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.db.get_value",
				side_effect=[employee, "CUST-001"],
			),
			patch(
				"phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.get_all",
				return_value=[],
			),
			patch(
				"phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.new_doc",
				return_value=fake,
			) as new_doc,
			patch("phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.db.commit"),
		):
			result = dap.start_project_timer(
				project_name="PROJ-001",
				expected_time=1800,
				goal="Investigate bug",
			)

		new_doc.assert_called_once_with("Timesheet Record")
		self.assertTrue(fake._inserted)
		self.assertEqual(result["name"], fake.name)
		self.assertEqual(result["session_state"], "running")
		self.assertEqual(result["project"], "PROJ-001")
		self.assertEqual(result["goal"], "Investigate bug")
		self.assertEqual(fake.project, "PROJ-001")
		self.assertEqual(fake.customer, "CUST-001")
		self.assertEqual(fake.employee, "EMP-001")
		self.assertEqual(fake.activity_type, "Development")
		self.assertEqual(fake.expected_time, 1800)
		self.assertFalse(getattr(fake, "gitlab_issue", None))
		self.assertEqual(len(fake.item), 1)

	def test_blocks_when_draft_already_exists(self):
		employee = SimpleNamespace(name="EMP-001", activity_type="Development")
		with (
			patch(
				"phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.db.get_value",
				return_value=employee,
			),
			patch(
				"phamos.phamos.page.dev_action_panel.dev_action_panel.frappe.get_all",
				return_value=[{"name": "TR-EXISTING"}],
			),
		):
			with self.assertRaises(frappe.ValidationError):
				dap.start_project_timer(
					project_name="PROJ-001",
					expected_time=1800,
					goal="Should fail",
				)
