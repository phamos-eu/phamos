"""Fill the new Value Add on existing Timesheet Records from Percent Billable (#1742, #1031 decision 4).

Until now Percent Billable was both the person's rating and the billing number. Value Add takes
over the rating: every record gets its Percent Billable as Value Add. Where the Implementation time
limit lowered Percent Billable, the comment "Percent billable reduced from X% to Y% …" keeps the
rating the person gave, so X is used. Percent Billable and everything billed from it stay as they are.
"""

import re

import frappe

REDUCED = re.compile(r"Percent billable reduced from (\d+)% to")


def execute():
	# Adding the column filled every row with the field default (100), so all rows are rewritten.
	frappe.db.sql(
		"""
		UPDATE `tabTimesheet Record`
		SET value_add = IF(percent_billable IN ('0', '25', '50', '75', '100'), percent_billable, '100')
		"""
	)

	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": "Timesheet Record",
			"comment_type": "Info",
			"content": ("like", "Percent billable reduced from %"),
		},
		fields=["reference_name", "content"],
		order_by="creation asc",
	)
	restored = set()
	for comment in comments:
		match = REDUCED.search(comment.content or "")
		# The first reduction holds the value the person picked; later ones start from a lowered value.
		if match and match.group(1) in ("0", "25", "50", "75", "100") and comment.reference_name not in restored:
			restored.add(comment.reference_name)
			frappe.db.set_value(
				"Timesheet Record", comment.reference_name, "value_add", match.group(1), update_modified=False
			)
