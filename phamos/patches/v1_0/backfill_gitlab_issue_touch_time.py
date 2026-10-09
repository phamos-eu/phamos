import frappe


def execute():
	"""Backfill GitLab Issue.total_touch_time for existing issues.

	The field only auto-updates going forward, via
	gitlab_utils.sync_touch_time_on_timesheet_change, whenever a linked Timesheet
	Record is next submitted or cancelled. Without this one-off backfill, issues
	closed before that hook existed would show blank until then, even though
	they already have counted Timesheet Records.
	"""
	frappe.db.sql("""
		UPDATE `tabGitLab Issue` gi
		JOIN (
			SELECT tr.gitlab_issue, SUM(tr.actual_time) AS touch_seconds
			FROM `tabTimesheet Record` tr
			JOIN `tabTimesheet` t ON t.name = tr.timesheet
			WHERE t.docstatus IN (0, 1) AND tr.gitlab_issue IS NOT NULL
			GROUP BY tr.gitlab_issue
		) touch ON touch.gitlab_issue = gi.name
		SET gi.total_touch_time = touch.touch_seconds
	""")
	frappe.db.commit()
