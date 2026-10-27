# Copyright (c) 2023, Phamos GmbH and Contributors
# See license.txt

"""Tests for Timesheet Record, including DAP/PAP create-path guards."""

from types import SimpleNamespace
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from phamos.phamos.page.dev_action_panel import dev_action_panel as dap
from phamos.phamos.page.project_action_panel import project_action_panel as pap
from phamos.phamos.timesheet_utils import normalize_percent_billable
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

# A user with the Employee role only. Timesheet Record create is limited to System Manager.
NO_ACCESS = "tr-no-access@example.com"


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
			patch(
				"phamos.phamos.page.project_action_panel.project_action_panel.frappe.db.get_value",
				side_effect=get_value,
			),
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
			) as get_all,
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

		get_all.assert_called_once_with(
			"Timesheet Record",
			filters={"employee": "EMP-001", "docstatus": 0},
			fields=["name"],
			limit=3,
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
			) as get_all,
		):
			with self.assertRaises(frappe.ValidationError):
				dap.start_project_timer(
					project_name="PROJ-001",
					expected_time=1800,
					goal="Should fail",
				)

		get_all.assert_called_once_with(
			"Timesheet Record",
			filters={"employee": "EMP-001", "docstatus": 0},
			fields=["name"],
			limit=3,
		)


class TestTimesheetRecordRules(FrappeTestCase):
	"""Acceptance criteria for Timesheet Record, checked test-last.

	1. A record with project, employee, goal, expected time and from time is saved as a draft.
	2. Submit without an end time is rejected, because the record is not marked complete.
	3. Submit with an end time but no activity type is rejected.
	4. One hour at 50% billable counts as 0.5 hours; 0% counts as 0.
	5. A user who is not a System Manager cannot create a record.
	"""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user("tr-employee@example.com")
		_ensure_user(NO_ACCESS)
		self.employee = _ensure_employee("tr-employee@example.com")
		self.activity_type = self._activity_type()
		self.project = self._project()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _activity_type(self):
		name = "TR Development"
		if not frappe.db.exists("Activity Type", name):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(ignore_permissions=True)
		return name

	def _project(self):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": "TR Rules project",
					"status": "Open",
					"project_owner": "Administrator",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _record(self, **overrides):
		values = {
			"doctype": "Timesheet Record",
			"project": self.project,
			"employee": self.employee,
			"goal": "Write the weekly report",
			"expected_time": 3600,
			"from_time": "2026-05-10 09:00:00",
			"activity_type": self.activity_type,
			"percent_billable": "100",
		}
		values.update(overrides)
		return frappe.get_doc(values)

	def test_valid_record_is_saved_as_draft(self):
		doc = self._record().insert(ignore_permissions=True)

		self.assertTrue(frappe.db.exists("Timesheet Record", doc.name))
		self.assertEqual(doc.docstatus, 0)
		self.assertEqual(doc.goal, "Write the weekly report")

	def test_submit_without_end_time_is_rejected(self):
		doc = self._record().insert(ignore_permissions=True)
		self.assertFalse(doc.to_time)

		with self.assertRaises(frappe.ValidationError):
			doc.submit()

		self.assertEqual(frappe.db.get_value("Timesheet Record", doc.name, "docstatus"), 0)

	def test_submit_without_activity_type_is_rejected(self):
		doc = self._record(activity_type=None, to_time="2026-05-10 10:00:00").insert(ignore_permissions=True)

		with self.assertRaises(frappe.ValidationError):
			doc.submit()

		self.assertEqual(frappe.db.get_value("Timesheet Record", doc.name, "docstatus"), 0)

	def test_billable_hours_follow_percent_billable(self):
		doc = self._record(actual_time=3600, percent_billable="50")
		self.assertEqual(doc.get_billable_hours(), 0.5)

		doc.percent_billable = "0"
		self.assertEqual(doc.get_billable_hours(), 0.0)

	def test_user_without_permission_cannot_create(self):
		frappe.set_user(NO_ACCESS)

		with self.assertRaises(frappe.PermissionError):
			self._record().insert()
