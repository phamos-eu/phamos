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
