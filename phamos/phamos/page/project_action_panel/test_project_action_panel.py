# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Project Action Panel: Value Add next to Percent Billable (#1745, parent #1031).

Both dialogs send Value Add; Percent Billable is kept as entered on every project, internal
ones included (revised decision 2 of #1031).
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.page.project_action_panel import project_action_panel as pap
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "pap-value-add@example.com"
RECORD = "phamos.phamos.doctype.timesheet_record.timesheet_record.TimesheetRecord"


class TestProjectActionPanelValueAdd(FrappeTestCase):
	def setUp(self):
		# create_timesheet builds the ERPNext Timesheet; not needed to check the record's ratings.
		for target in ("frappe.db.commit", f"{RECORD}.create_timesheet"):
			patcher = patch(target)
			patcher.start()
			self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)
		self.activity_type = "PAP Development"
		if not frappe.db.exists("Activity Type", self.activity_type):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": self.activity_type}).insert(ignore_permissions=True)
		self.internal = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"PAP Internal {frappe.generate_hash(length=5)}",
					"status": "Open",
					"custom_is_internal_project": 1,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _values(self, name):
		return tuple(frappe.db.get_value("Timesheet Record", name, ["percent_billable", "value_add"]))

	def test_create_and_submit_stores_value_add_and_keeps_billable_on_an_internal_project(self):
		frappe.set_user(USER)
		created = pap.create_and_submit_timesheet(
			project_name=self.internal,
			goal="Write the docs",
			from_time="2026-05-10 09:00:00",
			to_time="2026-05-10 10:00:00",
			expected_time=3600,
			percent_billable="100",
			activity_type=self.activity_type,
			result="Docs written",
			value_add="25",
		)
		self.assertEqual(created["status"], "success", created)
		self.assertEqual(self._values(created["name"]), ("100", "25"))

	def test_update_and_submit_stores_value_add(self):
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": self.internal,
				"employee": self.employee,
				"goal": "Fix the report",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
				"activity_type": self.activity_type,
			}
		)
		record.append("item", {"from_time": "2026-05-10 09:00:00"})
		record.insert(ignore_permissions=True)
		with patch.object(pap, "compute_time_limit_status", return_value={}):
			outcome = pap.update_and_submit_timesheet_record(
				record.name,
				"2026-05-10 10:00:00",
				"50",
				self.activity_type,
				"Report fixed",
				value_add="75",
			)
		self.assertEqual(outcome, {"timesheet_name": record.name})
		self.assertEqual(self._values(record.name), ("50", "75"))

	def test_update_and_submit_raises_errors_instead_of_reporting_success(self):
		# #1636: the panel showed "Updated Successfully" for any reply, also for an error text.
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": self.internal,
				"employee": self.employee,
				"goal": "Fix the report",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
				"activity_type": self.activity_type,
			}
		)
		record.append("item", {"from_time": "2026-05-10 09:00:00"})
		record.insert(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			pap.update_and_submit_timesheet_record(
				record.name, "2026-05-10 08:00:00", "50", self.activity_type, "Report fixed"
			)
		self.assertEqual(
			tuple(frappe.db.get_value("Timesheet Record", record.name, ["docstatus", "result"])), (0, None)
		)


class TestProjectActionPanelOneList(FrappeTestCase):
	"""One project list instead of "Your Projects" + "All Projects".

	Closing the assignment ToDo (e.g. "Mark as done" in the Personal Cockpit) used to drop the
	project from "Your Projects". Now every Open project is listed, plus projects assigned to me
	in any status: last used first, then assigned to me, then the rest.
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

	def _project(self, status="Open"):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"PAP List {frappe.generate_hash(length=6)}",
					"status": status,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _assign(self, project, status="Open"):
		return (
			frappe.get_doc(
				{
					"doctype": "ToDo",
					"status": status,
					"allocated_to": USER,
					"description": f"Assignment for Project {project}",
					"reference_type": "Project",
					"reference_name": project,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _listed(self):
		frappe.set_user(USER)
		rows = pap.fetch_projects()
		frappe.set_user("Administrator")
		return [row.name for row in rows], {row.name: row for row in rows}

	def test_open_project_not_assigned_to_me_is_listed(self):
		unassigned = self._project()
		names, _ = self._listed()
		self.assertIn(unassigned, names)

	def test_assigned_project_stays_listed_when_its_todo_is_closed(self):
		project = self._project()
		todo = self._assign(project)
		frappe.db.set_value("ToDo", todo, "status", "Closed")
		names, rows = self._listed()
		self.assertIn(project, names)
		self.assertEqual(rows[project].assigned_to_me, 0)

	def test_assigned_project_in_any_status_is_listed_before_unassigned_ones(self):
		unassigned = self._project()
		completed_mine = self._project(status="Completed")
		self._assign(completed_mine)
		names, rows = self._listed()
		self.assertIn(completed_mine, names)
		self.assertEqual(rows[completed_mine].assigned_to_me, 1)
		self.assertLess(names.index(completed_mine), names.index(unassigned))

	def test_last_used_project_comes_first(self):
		assigned = self._project()
		self._assign(assigned)
		used = self._project()
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": used,
				"employee": self.employee,
				"goal": "Last used",
				"expected_time": 3600,
				"from_time": "2026-05-10 09:00:00",
			}
		)
		record.append("item", {"from_time": "2026-05-10 09:00:00"})
		record.insert(ignore_permissions=True)
		names, _ = self._listed()
		self.assertLess(names.index(used), names.index(assigned))
