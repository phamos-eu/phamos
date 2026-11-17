"""Store Billable Hours on submitted Timesheet Records and switch Value Add billing on (#1746, #1031 decisions 10–11).

Billable time used to be calculated live as actual time × Percent Billable. It is now stored at submit
and, with the Phamos Settings switch on, includes Value Add. Old records get the value they were billed
with (actual time × Percent Billable, without Value Add), so past totals don't move.
"""

import frappe


def execute():
	# Percent Billable is a Select, stored as text. Records from the short-lived "Internal" option
	# (added in d61c0d0a, reverted in 369670d8) still hold that text, and MariaDB in strict mode refuses
	# arithmetic on it. Like compute_billable_hours (flt), anything that isn't a number counts as 0.
	frappe.db.sql(
		"""
		UPDATE `tabTimesheet Record`
		SET billable_hours = IFNULL(actual_time, 0) / 3600 * (
			CASE WHEN percent_billable REGEXP '^[0-9]+([.][0-9]+)?$'
			THEN CAST(percent_billable AS DECIMAL(10, 4)) ELSE 0 END
		) / 100
		WHERE docstatus = 1
		"""
	)
	frappe.db.set_single_value("Phamos Settings", "value_add_in_billing", 1)
