# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Developer Action Panel: project list, issue list, Percent Billable presets (0 when the project has none)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation
from phamos.phamos.page.dev_action_panel import dev_action_panel as dap
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "dap-value-add@example.com"


class _DapTestCase(FrappeTestCase):
	def setUp(self):
		for target in ("frappe.db.commit", "frappe.desk.form.assign_to.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, prefix="DAP", status="Open", percent_billable=None, **fields):
		name = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"{prefix} {frappe.generate_hash(length=6)}",
					"status": status,
					"project_owner": "Administrator",  # mandatory custom field
					**fields,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)
		if percent_billable is not None:
			frappe.db.set_value("Project", name, "percent_billable", percent_billable)
		return name

	def _assign(self, project):
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": USER,
				"reference_type": "Project",
				"reference_name": project,
				"description": "Assigned",
			}
		).insert(ignore_permissions=True)

	def _as_user(self, fn, *args, **kwargs):
		frappe.set_user(USER)
		try:
			return fn(*args, **kwargs)
		finally:
			frappe.set_user("Administrator")

	def _activity_type(self):
		name = "DAP Test Activity"
		if not frappe.db.exists("Activity Type", name):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": name}).insert(ignore_permissions=True)
		return name


class TestDevActionPanelBilling(_DapTestCase):
	def setUp(self):
		super().setUp()
		implementation = make_implementation().name
		self.billable = self._project("DAP Billable", percent_billable="75", custom_implementation=implementation)
		self.internal = self._project(
			"DAP Internal", percent_billable="75", custom_implementation=implementation, custom_is_internal_project=1
		)
		self.no_implementation = self._project("DAP Sales", percent_billable="")
		for project in (self.billable, self.internal, self.no_implementation):
			self._assign(project)

	def _presets(self, fetch):
		rows = {p["name"]: p for p in self._as_user(fetch)}
		return {name: rows[name]["percent_billable"] for name in (self.billable, self.internal, self.no_implementation)}

	def test_my_projects_carry_the_percent_billable_preset(self):
		self.assertEqual(
			self._presets(dap.get_dev_my_projects),
			{self.billable: "75", self.internal: "75", self.no_implementation: "0"},
		)

	def test_all_projects_carry_the_percent_billable_preset(self):
		self.assertEqual(
			self._presets(dap.get_dev_all_projects),
			{self.billable: "75", self.internal: "75", self.no_implementation: "0"},
		)

	def test_new_project_and_timesheet_record_default_to_zero_percent_billable(self):
		self.assertEqual(frappe.new_doc("Project").percent_billable, "0")
		self.assertEqual(frappe.new_doc("Timesheet Record").percent_billable, "0")

	def test_project_without_percent_billable_presets_zero_everywhere(self):
		from phamos.api import personal_timer
		from phamos.phamos.timesheet_utils import billing_context

		self.assertEqual(billing_context(self.no_implementation), {"percent_billable": "0"})
		self.assertEqual(billing_context(None), {"percent_billable": "0"})
		info = self._as_user(personal_timer.get_timer_project_info, self.no_implementation)
		self.assertEqual(info["percent_billable"], "0")

	def test_issue_timer_carries_its_project_preset(self):
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": self.employee,
				"project": self.billable,
				"goal": "Issue work",
				"expected_time": 3600,
				"from_time": frappe.utils.now_datetime(),
				"gitlab_issue": "DAP-ISSUE-1",
			}
		)
		record.append("item", {"from_time": record.from_time})
		record.flags.ignore_links = True  # the panel only reads the field
		record.insert(ignore_permissions=True)
		self.assertEqual(self._as_user(dap.get_active_session)["project_percent_billable"], "75")


class TestDevActionPanelOneProjectList(_DapTestCase):
	"""Every Open project plus mine in any status; last used first, then assigned to me, then the rest."""

	def _listed(self):
		rows = self._as_user(dap.get_dev_all_projects)
		return [row["name"] for row in rows], {row["name"]: row for row in rows}

	def test_assigned_project_in_any_status_is_listed_before_unassigned_ones(self):
		unassigned = self._project()
		completed_mine = self._project(status="Completed")
		self._assign(completed_mine)
		names, rows = self._listed()
		self.assertIn(completed_mine, names)
		self.assertEqual(rows[completed_mine]["is_assigned"], 1)
		self.assertLess(names.index(completed_mine), names.index(unassigned))

	def test_project_with_two_open_todos_is_listed_once(self):
		project = self._project()
		self._assign(project)
		self._assign(project)
		names, _ = self._listed()
		self.assertEqual(names.count(project), 1)

	def test_last_used_project_comes_first(self):
		# By name "A…" would come first; only "last used first" puts "Z…" on top.
		unused = self._project(prefix="DAP List A")
		used = self._project(prefix="DAP List Z")
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": self.employee,
				"project": used,
				"goal": "Last used",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
			}
		)
		record.append("item", {"from_time": "2026-05-10 09:00:00"})
		record.insert(ignore_permissions=True)
		names, _ = self._listed()
		self.assertLess(names.index(used), names.index(unused))

	def test_project_timer_starts_at_the_chosen_time(self):
		started = self._as_user(
			dap.start_project_timer, self._project(), 3600, "Backdated", manual_start_time="2026-05-10 08:15:00"
		)
		self.assertEqual(str(frappe.db.get_value("Timesheet Record", started["name"], "from_time")), "2026-05-10 08:15:00")


class TestDevActionPanelIssueList(_DapTestCase):
	def setUp(self):
		super().setUp()
		self.project = self._project("DAP Issues")

	def _issue(self, title, parent=None, due_date="2026-01-01"):
		# No gitlab_project, so the name is a hash and nothing is pushed to GitLab.
		return frappe.get_doc(
			{
				"doctype": "GitLab Issue",
				"title": title,
				"state": "opened",
				"due_date": due_date,
				"parent_issue": parent,
				"assignee_email": "someone.else@example.com",
			}
		).insert(ignore_permissions=True).name

	def _issues(self):
		return {row["name"]: row for row in self._as_user(dap.get_my_issues)}

	def test_running_issue_assigned_to_someone_else_is_marked_running(self):
		running = self._issue("Running, not assigned to me")
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"employee": self.employee,
				"project": self.project,
				"goal": "Running",
				"expected_time": 3600,
				"from_time": frappe.utils.now_datetime(),
				"gitlab_issue": running,
			}
		)
		record.append("item", {"from_time": record.from_time})
		record.insert(ignore_permissions=True)
		row = self._issues()[running]
		self.assertEqual(row["session_state"], "running")
		self.assertEqual(row["active_timesheet"], record.name)
		self.assertFalse(row["is_mine"])

	def test_issues_carry_child_count_and_parent(self):
		parent = self._issue("Parent")
		child = self._issue("Child", parent=parent)
		self._issue("Second child", parent=parent)
		rows = self._issues()
		self.assertEqual(rows[parent]["child_count"], 2)
		self.assertEqual(rows[child]["child_count"], 0)
		self.assertEqual(rows[child]["parent_issue_title"], "Parent")

	def test_start_issue_timer_on_an_issue_not_assigned_to_me(self):
		frappe.db.set_value("Employee", self.employee, "activity_type", None)
		gitlab_project = frappe.get_doc(
			{
				"doctype": "GitLab Project",
				"title": "DAP GP",
				"project_id": frappe.generate_hash(length=10),
				"frappe_project": self.project,
			}
		)
		gitlab_project.flags.ignore_mandatory = True
		gitlab_project.insert(ignore_permissions=True)
		issue = self._issue("Customer parent ticket")
		frappe.db.set_value("GitLab Issue", issue, "gitlab_project", gitlab_project.name)

		row = self._issues()[issue]
		self.assertEqual(row["project"], self.project)
		self.assertEqual(row["project_name"], frappe.db.get_value("Project", self.project, "project_name"))
		self.assertEqual(row["gitlab_project_title"], "DAP GP")

		started = self._as_user(dap.start_issue_timer, issue, 3600)
		self.assertEqual(frappe.db.get_value("Timesheet Record", started["name"], "gitlab_issue"), issue)


class TestDevActionPanelStopPreset(_DapTestCase):
	"""Without a Percent Billable, a timer or break takes the project's preset, 0 when it has none."""

	def test_project_timer_draft_carries_the_project_preset(self):
		empty = self._as_user(dap.start_project_timer, self._project(percent_billable=""), 3600, "No preset")
		self.assertEqual(frappe.db.get_value("Timesheet Record", empty["name"], "percent_billable"), "0")
		frappe.db.delete("Timesheet Record", empty["name"])  # one draft per employee
		half = self._as_user(dap.start_project_timer, self._project(percent_billable="50"), 3600, "Half")
		self.assertEqual(frappe.db.get_value("Timesheet Record", half["name"], "percent_billable"), "50")

	def test_break_without_percent_billable_uses_the_project_preset(self):
		args = {"goal": "g", "result": "r", "activity_type": self._activity_type()}
		none = self._as_user(
			dap.create_break_timesheet, "2026-05-10 09:00:00", "2026-05-10 09:30:00",
			project=self._project(percent_billable=""), **args,
		)
		half = self._as_user(
			dap.create_break_timesheet, "2026-05-10 10:00:00", "2026-05-10 10:30:00",
			project=self._project(percent_billable="50"), **args,
		)
		self.assertEqual(frappe.db.get_value("Timesheet Record", none["name"], "percent_billable"), "0")
		self.assertEqual(frappe.db.get_value("Timesheet Record", half["name"], "percent_billable"), "50")
