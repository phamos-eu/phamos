"""Store Billable Hours on submitted Timesheet Records and switch Value Add billing on (#1746, #1031 decisions 10–11).

Billable time used to be calculated live as actual time × Percent Billable. It is now stored at submit
and, with the Phamos Settings switch on, includes Value Add. Old records get the value they were billed
with (actual time × Percent Billable, without Value Add), so past totals don't move.
"""

import frappe


def execute():
	frappe.db.sql(
		"""
		UPDATE `tabTimesheet Record`
		SET billable_hours = IFNULL(actual_time, 0) / 3600 * IFNULL(percent_billable, 0) / 100
		WHERE docstatus = 1
		"""
	)
	frappe.db.set_single_value("Phamos Settings", "value_add_in_billing", 1)
