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


def _make_billable_implementation():
	"""An Implementation for a test customer, so a Project linked to it is billable (#1742)."""
	from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation

	return make_implementation().name


class TestValueAddAndBillingRules(FrappeTestCase):
	"""Value Add next to Percent Billable (#1031, child #1742).

	1. Percent Billable is kept as entered on every project, internal ones included, because
	   external people may bill there too (revised decision 2 of #1031); preset from the Project, 100 when empty.
	2. Value Add is one of 0/25/50/75/100; empty becomes 100.
	3. The time limit lowers only Percent Billable.
	4. The shared timer backend stores Value Add on stops and tracked breaks.
	"""

	USER = "va-employee@example.com"

	def setUp(self):
		for target in ("frappe.db.commit", "frappe.desk.form.assign_to.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(self.USER)
		_ensure_user(NO_ACCESS)
		self.employee = _ensure_employee(self.USER)
		self.activity_type = "VA Development"
		if not frappe.db.exists("Activity Type", self.activity_type):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": self.activity_type}).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", self.employee, "activity_type", self.activity_type)
		self.implementation = _make_billable_implementation()
		self.billable = self._project("VA Billable", implementation=self.implementation)
		self.internal = self._project("VA Internal", implementation=self.implementation, internal=1)
		self.no_implementation = self._project("VA No Implementation")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, project_name, implementation=None, internal=0, percent_billable="75"):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"{project_name} {frappe.generate_hash(length=5)}",
					"status": "Open",
					"custom_implementation": implementation,
					"custom_is_internal_project": internal,
					"percent_billable": percent_billable,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _record(self, project, **overrides):
		values = {
			"doctype": "Timesheet Record",
			"project": project,
			"employee": self.employee,
			"goal": "Value Add test",
			"expected_time": 3600,
			"from_time": "2026-05-10 09:00:00",
			"activity_type": self.activity_type,
			"percent_billable": "75",
		}
		values.update(overrides)
		return frappe.get_doc(values).insert(ignore_permissions=True)

	def test_billing_context_presets_from_the_project(self):
		from phamos.phamos.timesheet_utils import get_billing_context

		self.assertEqual(get_billing_context(self.billable), {"percent_billable": "75"})
		self.assertEqual(get_billing_context(self.internal), {"percent_billable": "75"})
		no_preset = self._project("VA No Preset", percent_billable="")
		self.assertEqual(get_billing_context(no_preset), {"percent_billable": "100"})

	def test_billing_context_needs_read_access_to_the_project(self):
		from phamos.phamos.timesheet_utils import get_billing_context

		frappe.set_user(NO_ACCESS)
		with self.assertRaises(frappe.PermissionError):
			get_billing_context(self.billable)

	def test_empty_percent_billable_on_a_billable_project_becomes_zero(self):
		self.assertEqual(self._record(self.billable, percent_billable="").percent_billable, "0")

	def test_percent_billable_is_kept_on_a_billable_project(self):
		self.assertEqual(self._record(self.billable, percent_billable="50").percent_billable, "50")

	def test_percent_billable_is_kept_on_an_internal_project(self):
		self.assertEqual(self._record(self.internal, percent_billable="100").percent_billable, "100")

	def test_percent_billable_is_kept_without_an_implementation(self):
		self.assertEqual(self._record(self.no_implementation, percent_billable="25").percent_billable, "25")

	def test_value_add_defaults_to_100_and_is_kept(self):
		self.assertEqual(self._record(self.billable).value_add, "100")
		self.assertEqual(self._record(self.internal, value_add="25").value_add, "25")
		self.assertEqual(self._record(self.billable, value_add="").value_add, "100")

	def test_value_add_outside_the_options_is_rejected(self):
		with self.assertRaises(frappe.ValidationError):
			self._record(self.billable, value_add="33")

	def test_time_limit_lowers_only_percent_billable(self):
		from phamos.phamos.doctype.timesheet_record import timesheet_record as tr

		doc = self._record(self.billable, percent_billable="100", value_add="75", to_time="2026-05-10 11:00:00", actual_time=7200)
		details = frappe._dict(limit_hours=1, from_date="2026-05-01", to_date="2026-05-31")
		with patch.object(tr, "get_enforced_time_limit_details", return_value=details), patch.object(
			tr, "get_billable_hours_in_period_for_implementation", return_value=0
		), patch.object(tr.TimesheetRecord, "check_implementation_time_limit"), patch.object(
			tr.TimesheetRecord, "create_timesheet"
		):
			tr.submit_at_available_hours(doc.name)
		values = frappe.db.get_value("Timesheet Record", doc.name, ["percent_billable", "value_add"])
		self.assertEqual(tuple(values), ("50", "75"))

	def _start(self, project):
		frappe.set_user(self.USER)
		dap.start_project_timer(project, 3600, "Value Add timer")
		return dap.get_active_project_session()

	def test_active_project_session_carries_the_project_preset(self):
		session = self._start(self.internal)
		self.assertEqual(session["project_percent_billable"], "75")
		self.assertNotIn("project_is_billable", session)

	def test_stop_timer_stores_value_add(self):
		name = self._start(self.billable)["name"]
		with patch.object(dap, "compute_time_limit_status", return_value={}), patch(
			"phamos.phamos.doctype.timesheet_record.timesheet_record.TimesheetRecord.create_timesheet"
		):
			dap.stop_timer(name, "Done", percent_billable="50", value_add="25", activity_type=self.activity_type)
		values = frappe.db.get_value("Timesheet Record", name, ["percent_billable", "value_add"])
		self.assertEqual(tuple(values), ("50", "25"))

	def test_break_timesheet_stores_value_add(self):
		frappe.set_user(self.USER)
		with patch("phamos.phamos.doctype.timesheet_record.timesheet_record.TimesheetRecord.create_timesheet"):
			created = dap.create_break_timesheet(
				"2026-05-10 09:00:00", "2026-05-10 09:30:00", project=self.internal, goal="Call", result="Agreed",
				percent_billable=100, value_add=50, activity_type=self.activity_type,
			)
		values = frappe.db.get_value("Timesheet Record", created["name"], ["percent_billable", "value_add"])
		self.assertEqual(tuple(values), ("100", "50"))


class TestCopyPercentBillableToValueAddPatch(FrappeTestCase):
	"""Patch copy_percent_billable_to_value_add (#1742, decision 4 of #1031)."""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user("va-patch@example.com")
		self.employee = _ensure_employee("va-patch@example.com")
		self.project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"VA Patch {frappe.generate_hash(length=5)}", "status": "Open"}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.db.rollback()

	def _record(self, percent_billable):
		doc = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": self.project,
				"employee": self.employee,
				"goal": "Patch test",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
			}
		).insert(ignore_permissions=True)
		# Old data: the column was just added with its default, and the billing value differs.
		frappe.db.set_value("Timesheet Record", doc.name, {"percent_billable": percent_billable, "value_add": "100"}, update_modified=False)
		return doc

	def test_copies_percent_billable_and_restores_the_value_before_the_time_limit(self):
		from phamos.patches.v1_0 import copy_percent_billable_to_value_add

		plain = self._record("50")
		lowered = self._record("25")
		lowered.add_comment("Info", "Percent billable reduced from 75% to 25% to fit the 10h time limit for 2026-05-01 to 2026-05-31. From/To Time were kept exactly as logged.")

		copy_percent_billable_to_value_add.execute()

		self.assertEqual(frappe.db.get_value("Timesheet Record", plain.name, ["percent_billable", "value_add"]), ("50", "50"))
		self.assertEqual(frappe.db.get_value("Timesheet Record", lowered.name, ["percent_billable", "value_add"]), ("25", "75"))


class TestBillableHoursWithValueAdd(FrappeTestCase):
	"""Value Add in billing, stored at submit, switch in Phamos Settings (#1746, #1031 decisions 9–11).

	1. Switch on: billable hours = actual time × Percent Billable × Value Add; off: without Value Add.
	2. The result is stored on submit; flipping the switch later does not change it.
	3. The ERPNext Timesheet and the time-limit usage read the stored value.
	4. "Submit at available hours" counts Value Add when picking the Percent Billable tier.
	"""

	USER = "bh-employee@example.com"

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(self.USER)
		self.employee = _ensure_employee(self.USER)
		self.activity_type = "BH Development"
		if not frappe.db.exists("Activity Type", self.activity_type):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": self.activity_type}).insert(ignore_permissions=True)
		self.implementation = _make_billable_implementation()
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"BH Project {frappe.generate_hash(length=5)}",
					"status": "Open",
					"custom_implementation": self.implementation,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		self._switch(1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _switch(self, on):
		frappe.db.set_single_value("Phamos Settings", "value_add_in_billing", on)

	def _record(self, percent_billable="100", value_add="50", hours=2, submit=True):
		doc = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": self.project,
				"employee": self.employee,
				"goal": "Billing test",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
				"to_time": f"2026-05-10 {9 + hours:02d}:00:00",
				"actual_time": hours * 3600,
				"activity_type": self.activity_type,
				"percent_billable": percent_billable,
				"value_add": value_add,
			}
		).insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	def test_switch_on_multiplies_value_add(self):
		self.assertEqual(self._record().billable_hours, 1.0)

	def test_switch_off_leaves_value_add_out(self):
		self._switch(0)
		self.assertEqual(self._record().billable_hours, 2.0)

	def test_stored_value_survives_flipping_the_switch(self):
		doc = self._record()
		self._switch(0)
		doc.reload()
		self.assertEqual((doc.billable_hours, doc.get_billable_hours()), (1.0, 1.0))

	def test_erpnext_timesheet_bills_the_stored_hours(self):
		doc = self._record(percent_billable="50", value_add="50", hours=4)
		billing = frappe.get_all("Timesheet Detail", filters={"parent": doc.timesheet}, pluck="billing_hours")
		self.assertEqual(billing, [1.0])

	def test_time_limit_usage_sums_the_stored_hours(self):
		from phamos.phamos.doctype.timesheet_record.timesheet_record import get_billable_hours_in_period_for_implementation

		self._record()
		self._switch(0)
		self.assertEqual(get_billable_hours_in_period_for_implementation(self.implementation, "2026-05-01", "2026-05-31"), 1.0)

	def test_submit_at_available_hours_counts_value_add(self):
		from phamos.phamos.doctype.timesheet_record import timesheet_record as tr

		doc = self._record(submit=False)  # 2 h, Value Add 50
		details = frappe._dict(limit_hours=0.5, from_date="2026-05-01", to_date="2026-05-31")
		with patch.object(tr, "get_enforced_time_limit_details", return_value=details), patch.object(
			tr, "get_billable_hours_in_period_for_implementation", return_value=0
		), patch.object(tr.TimesheetRecord, "check_implementation_time_limit"):
			tr.submit_at_available_hours(doc.name)
		# 2 h × 50 % × 50 % = 0.5 h fits; without Value Add only 25 % would.
		self.assertEqual(frappe.db.get_value("Timesheet Record", doc.name, ["percent_billable", "billable_hours"]), ("50", 0.5))

	def test_dev_action_panel_stats_use_the_stored_hours(self):
		self._record(hours=2)
		frappe.set_user(self.USER)
		with patch("frappe.utils.nowdate", return_value="2026-05-10"):
			stats = dap.get_time_stats()
		self.assertEqual(stats["today"]["billable_seconds"], 3600)


class TestSetTimesheetRecordBillableHoursPatch(FrappeTestCase):
	"""Patch set_timesheet_record_billable_hours (#1746, #1031 decision 10)."""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def test_old_records_get_actual_time_times_percent_billable_without_value_add(self):
		from phamos.patches.v1_0 import set_timesheet_record_billable_hours

		name = frappe.get_all("Timesheet Record", filters={"docstatus": 1}, pluck="name", limit=1)
		if not name:
			self.skipTest("needs one submitted Timesheet Record")
		name = name[0]
		frappe.db.set_value(
			"Timesheet Record", name, {"actual_time": 3600, "percent_billable": "50", "value_add": "50", "billable_hours": 0}, update_modified=False
		)
		frappe.db.set_single_value("Phamos Settings", "value_add_in_billing", 0)

		set_timesheet_record_billable_hours.execute()

		self.assertEqual(frappe.db.get_value("Timesheet Record", name, "billable_hours"), 0.5)
		self.assertEqual(frappe.db.get_single_value("Phamos Settings", "value_add_in_billing"), 1)
