# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Dev and Sales Action Panel data for Value Add next to Percent Billable (#1744, parent #1031).

The panels show Percent Billable only for billable projects (an Implementation, not internal),
so project rows and the issue timer say whether their project is billable and give its preset.
"""

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
		self.no_implementation = self._project("DAP Sales")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _project(self, project_name, implementation=None, internal=0):
		name = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"{project_name} {frappe.generate_hash(length=5)}",
					"status": "Open",
					"custom_implementation": implementation,
					"custom_is_internal_project": internal,
					"percent_billable": "75",
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
		return {name: (rows[name]["is_billable"], rows[name]["percent_billable"]) for name in (self.billable, self.internal, self.no_implementation)}

	def test_my_projects_say_whether_they_are_billable(self):
		self.assertEqual(
			self._rows(dap.get_dev_my_projects),
			{self.billable: (True, "75"), self.internal: (False, "0"), self.no_implementation: (False, "0")},
		)

	def test_all_projects_say_whether_they_are_billable(self):
		self.assertEqual(
			self._rows(dap.get_dev_all_projects),
			{self.billable: (True, "75"), self.internal: (False, "0"), self.no_implementation: (False, "0")},
		)

	def test_issue_timer_says_whether_its_project_is_billable(self):
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
		self.assertEqual((session["project_is_billable"], session["project_percent_billable"]), (True, "75"))
