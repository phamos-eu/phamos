# Copyright (c) 2025, Phamos and contributors
# For license information, please see license.txt

"""
Migration patch to update existing parent OKRs to have is_group = 1.

This patch:
1. Finds all OKRs that have children (are parents)
2. Sets is_group = 1 on those parent OKRs if not already set
3. This ensures tree view works correctly for existing data
"""

import frappe


def execute():
	"""Update existing parent OKRs to have is_group = 1"""

	try:
		# Find all OKRs that have children (are parents)
		parent_okrs = frappe.db.sql("""
			SELECT DISTINCT parent_okr
			FROM `tabOKR`
			WHERE parent_okr IS NOT NULL AND parent_okr != ''
		""", as_list=True)

		updated_count = 0
		not_found = []

		for parent_okr_tuple in parent_okrs:
			parent_okr = parent_okr_tuple[0] if parent_okr_tuple else None
			if not parent_okr:
				continue
			# Check if parent OKR exists
			if not frappe.db.exists("OKR", parent_okr):
				not_found.append(parent_okr)
				continue

			# Check current is_group value
			parent_is_group = frappe.db.get_value("OKR", parent_okr, "is_group")

			# Update if not already set to 1
			if not parent_is_group:
				frappe.db.set_value("OKR", parent_okr, "is_group", 1, update_modified=False)
				updated_count += 1

		frappe.db.commit()

		# Log results
		if updated_count > 0:
			frappe.log_error(
				f"Updated {updated_count} parent OKRs to is_group = 1",
				"OKR parent is_group update: Success"
			)
		if not_found:
			frappe.log_error(
				f"Parent OKRs not found: {', '.join(not_found)}",
				"OKR parent is_group update: Missing parents"
			)
	except Exception as e:
		frappe.log_error(
			"Error updating parent OKRs is_group",
			f"OKR parent is_group update failed: {str(e)}"
		)
		raise
