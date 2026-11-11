# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Project Action Panel on version-15: Stop → Update reports errors (#1636).

develop's file of the same name also tests Value Add (#1745) and the one project list
(#1819); neither is on version-15, so only the #1636 test is here.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.page.project_action_panel import project_action_panel as pap
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "pap-update@example.com"
RECORD = "phamos.phamos.doctype.timesheet_record.timesheet_record.TimesheetRecord"


class TestProjectActionPanelUpdate(FrappeTestCase):
	def setUp(self):
		# create_timesheet builds the ERPNext Timesheet; not needed to check the record.
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
		self.project = (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"PAP Update {frappe.generate_hash(length=5)}",
					"status": "Open",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_update_and_submit_raises_errors_instead_of_reporting_success(self):
		# #1636: the panel showed "Updated Successfully" for any reply, also for an error text.
		record = frappe.get_doc(
			{
				"doctype": "Timesheet Record",
				"project": self.project,
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
