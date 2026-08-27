"""Remap legacy Risk Register Entry Status values to the new option set.

"Not Started" was replaced by "Identified" and "Closed" was replaced by
"Mitigated" when "Realised" was added to the Status options. Existing rows
still hold the old values, which are no longer valid Select options and would
fail validation the next time the record is opened and saved.
"""

import frappe


def execute():
	frappe.db.sql(
		"""UPDATE `tabRisk Register Entry` SET status = 'Identified' WHERE status = 'Not Started'"""
	)
	frappe.db.sql(
		"""UPDATE `tabRisk Register Entry` SET status = 'Mitigated' WHERE status = 'Closed'"""
	)
