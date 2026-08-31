import frappe


def execute():
	"""Backfill GitLab Issue.aging_days for existing closed issues.

	Matches DATEDIFF(DATE(closed_at), DATE(created_at)), the same formula the
	dashboard's Aging buckets already use, so aging_days can now back those
	buckets as a real, filterable field instead of a value computed on the fly.
	"""
	frappe.db.sql("""
		UPDATE `tabGitLab Issue`
		SET aging_days = DATEDIFF(DATE(closed_at), DATE(created_at))
		WHERE state = 'closed' AND closed_at IS NOT NULL AND created_at IS NOT NULL
	""")
	frappe.db.commit()
