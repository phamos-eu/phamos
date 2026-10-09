import frappe


def execute():
	"""Recompute GitLab Issue.cycle_time_started_at for every issue that already
	has a Cycle Start Label Set At, now that gitlab_utils.sync_cycle_time_start
	also caps its search at closed_at (not just floors it at the label
	timestamp). Before this fix, a Timesheet Record logged after closed_at
	(bad/retroactive data) could get picked as the earliest one and resolve a
	cycle_time_started_at later than the issue's own Cycle Time end point,
	showing up as a negative Cycle Time on the dashboard. This mirrors that
	same resolver as a bulk update so already-closed issues don't have to wait
	for their next Timesheet Record to get corrected.
	"""
	frappe.db.sql("""
		UPDATE `tabGitLab Issue` gi
		LEFT JOIN (
			SELECT tr.gitlab_issue, MIN(tr.from_time) AS started_at
			FROM `tabTimesheet Record` tr
			JOIN `tabTimesheet` t ON t.name = tr.timesheet
			JOIN `tabGitLab Issue` ce_gi ON ce_gi.name = tr.gitlab_issue
			WHERE t.docstatus IN (0, 1)
			  AND tr.from_time >= ce_gi.cycle_start_label_set_at
			  AND (ce_gi.closed_at IS NULL OR tr.to_time <= ce_gi.closed_at)
			GROUP BY tr.gitlab_issue
		) started ON started.gitlab_issue = gi.name
		SET gi.cycle_time_started_at = started.started_at
		WHERE gi.cycle_start_label_set_at IS NOT NULL
	""")
	frappe.db.commit()
