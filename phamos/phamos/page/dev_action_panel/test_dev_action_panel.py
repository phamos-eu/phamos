# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Dev and Sales Action Panel data for Value Add next to Percent Billable (#1744, parent #1031).

The panels show Percent Billable on every project (external people may bill internal projects
too), preset from the project, so project rows and the issue timer carry that preset (0 when empty, #1862).
"""

import random
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation
from phamos.phamos.page.dev_action_panel import dev_action_panel as dap
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "dap-value-add@example.com"


class TestDevActionPanelBilling(FrappeTestCase):
	def setUp(self):
		for target in ("frappe.db.commit", "frappe.desk.form.assign_to.notify_assignment"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)
		implementation = make_implementation().name
		self.billable = self._project("DAP Billable", implementation=implementation)
		self.internal = self._project("DAP Internal", implementation=implementation, internal=1)
		self.no_implementation = self._project("DAP Sales", percent_billable="")
		# No value at all, not even the field default: the panel presets 0 (#1862).
		frappe.db.set_value("Project", self.no_implementation, "percent_billable", "")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, project_name, implementation=None, internal=0, percent_billable="75"):
		name = (
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
		frappe.get_doc(
			{"doctype": "ToDo", "allocated_to": USER, "reference_type": "Project", "reference_name": name, "description": "Assigned"}
		).insert(ignore_permissions=True)
		return name

	def _rows(self, fetch):
		frappe.set_user(USER)
		rows = {p["name"]: p for p in fetch()}
		return {name: rows[name]["percent_billable"] for name in (self.billable, self.internal, self.no_implementation)}

	def test_my_projects_carry_the_percent_billable_preset(self):
		self.assertEqual(
			self._rows(dap.get_dev_my_projects),
			{self.billable: "75", self.internal: "75", self.no_implementation: "0"},
		)

	def test_all_projects_carry_the_percent_billable_preset(self):
		self.assertEqual(
			self._rows(dap.get_dev_all_projects),
			{self.billable: "75", self.internal: "75", self.no_implementation: "0"},
		)

	def test_a_new_project_defaults_to_zero_percent_billable(self):
		# #1862: the Project field default is 0, not a hard-coded 100.
		self.assertEqual(frappe.new_doc("Project").percent_billable, "0")

	def test_project_without_percent_billable_presets_zero_everywhere(self):
		from phamos.api import personal_timer
		from phamos.phamos.timesheet_utils import billing_context

		self.assertEqual(billing_context(self.no_implementation), {"percent_billable": "0"})
		self.assertEqual(billing_context(None), {"percent_billable": "0"})
		frappe.set_user(USER)
		self.assertEqual(personal_timer.get_timer_project_info(self.no_implementation)["percent_billable"], "0")

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
		record.flags.ignore_links = True  # no GitLab Issue record needed; the panel only reads the field
		record.insert(ignore_permissions=True)
		frappe.set_user(USER)
		session = dap.get_active_session()
		self.assertEqual(session["project_percent_billable"], "75")


class TestDevActionPanelOneProjectList(FrappeTestCase):
	"""One project list instead of "My Projects" + "All Projects" (as in the Project Action Panel, !1128).

	Every Open project, plus projects assigned to me in any status; last used first, then assigned
	to me, then the rest. Closing the assignment ToDo only changes the order.
	"""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, status="Open", prefix="DAP List"):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"{prefix} {frappe.generate_hash(length=6)}",
					"status": status,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _assign(self, project):
		return (
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"allocated_to": USER,
					"reference_type": "Project",
					"reference_name": project,
					"description": "Assigned",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _listed(self):
		frappe.set_user(USER)
		rows = dap.get_dev_all_projects()
		frappe.set_user("Administrator")
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
		# Neither is assigned; by name "A…" would come first, so only "last used first" puts "Z…" on top.
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
		project = self._project()
		frappe.set_user(USER)
		started = dap.start_project_timer(project, 3600, "Backdated", manual_start_time="2026-05-10 08:15:00")
		frappe.set_user("Administrator")
		self.assertEqual(str(frappe.db.get_value("Timesheet Record", started["name"], "from_time")), "2026-05-10 08:15:00")


class TestDevActionPanelIssueList(FrappeTestCase):
	"""#1862: the issue with my running timer comes first; issues say whether they are parents."""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)
		self.project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"DAP Issues {frappe.generate_hash(length=6)}", "status": "Open"}
		).insert(ignore_permissions=True).name

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _issue(self, title, parent=None, due_date="2026-01-01"):
		# No gitlab_project, so the name is a hash; nothing is pushed to GitLab.
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
		frappe.set_user(USER)
		rows = dap.get_my_issues()
		frappe.set_user("Administrator")
		return rows

	def test_issue_with_my_running_timer_comes_first(self):
		self._issue("Due early")  # would come first by due date
		running = self._issue("Running, not assigned to me", due_date="2099-12-31")
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
		rows = self._issues()
		self.assertEqual(rows[0]["name"], running)
		self.assertEqual(rows[0]["session_state"], "running")
		self.assertFalse(rows[0]["is_mine"])  # a PM can run a timer on an issue assigned to someone else

	def test_issues_carry_their_child_count(self):
		parent = self._issue("Parent")
		child = self._issue("Child", parent=parent)
		self._issue("Second child", parent=parent)
		rows = {r["name"]: r for r in self._issues()}
		self.assertEqual(rows[parent]["child_count"], 2)
		self.assertEqual(rows[child]["child_count"], 0)
		self.assertEqual(rows[child]["parent_issue"], parent)

	def test_start_issue_timer_on_an_issue_not_assigned_to_me(self):
		frappe.db.set_value("Employee", self.employee, "activity_type", None)
		gitlab_project = frappe.get_doc(
			{
				"doctype": "GitLab Project",
				"title": f"DAP GP {frappe.generate_hash(length=6)}",
				"project_id": str(random.randint(900000, 999999)),
				"frappe_project": self.project,
			}
		)
		gitlab_project.flags.ignore_mandatory = True
		gitlab_project.insert(ignore_permissions=True)
		issue = self._issue("Customer parent ticket")
		frappe.db.set_value("GitLab Issue", issue, "gitlab_project", gitlab_project.name)
		# The issue carries its ERPNext project, so the project filter can find it (#1862).
		row = next(r for r in self._issues() if r["name"] == issue)
		self.assertEqual(row["project"], self.project)
		self.assertEqual(row["project_name"], frappe.db.get_value("Project", self.project, "project_name"))
		frappe.set_user(USER)
		started = dap.start_issue_timer(issue, 3600)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Timesheet Record", started["name"], "gitlab_issue"), issue)


class TestDevActionPanelStopPreset(FrappeTestCase):
	"""#1862: a stop or break without a Percent Billable takes the project's preset, 0 when it has none."""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, percent_billable):
		name = frappe.get_doc(
			{"doctype": "Project", "project_name": f"DAP Preset {frappe.generate_hash(length=6)}", "status": "Open"}
		).insert(ignore_permissions=True).name
		frappe.db.set_value("Project", name, "percent_billable", percent_billable)
		return name

	def test_a_new_timesheet_record_defaults_to_zero_percent_billable(self):
		# #1862: the Timesheet Record field default is 0, not a hard-coded 100.
		self.assertEqual(frappe.new_doc("Timesheet Record").percent_billable, "0")

	def test_project_timer_draft_carries_the_project_preset(self):
		frappe.set_user(USER)
		empty = dap.start_project_timer(self._project(""), 3600, "No preset")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Timesheet Record", empty["name"], "percent_billable"), "0")
		frappe.db.delete("Timesheet Record", empty["name"])  # one draft per employee
		frappe.set_user(USER)
		half = dap.start_project_timer(self._project("50"), 3600, "Half")
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Timesheet Record", half["name"], "percent_billable"), "50")

	def test_break_without_percent_billable_uses_the_project_preset(self):
		activity = "DAP Preset Activity"
		if not frappe.db.exists("Activity Type", activity):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": activity}).insert(ignore_permissions=True)
		args = {"goal": "g", "result": "r", "activity_type": activity}
		frappe.set_user(USER)
		none = dap.create_break_timesheet("2026-05-10 09:00:00", "2026-05-10 09:30:00", project=self._project(""), **args)
		half = dap.create_break_timesheet("2026-05-10 10:00:00", "2026-05-10 10:30:00", project=self._project("50"), **args)
		frappe.set_user("Administrator")
		self.assertEqual(frappe.db.get_value("Timesheet Record", none["name"], "percent_billable"), "0")
		self.assertEqual(frappe.db.get_value("Timesheet Record", half["name"], "percent_billable"), "50")
