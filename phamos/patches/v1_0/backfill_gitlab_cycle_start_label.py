import frappe


def execute():
	"""Queue a one-off backfill of GitLab Issue.cycle_start_label_set_at (and the
	Cycle Time Started At it drives) from GitLab's Resource Label Events API.

	The field only auto-fills going forward, via
	gitlab_utils.sync_cycle_start_label_from_gitlab, called from the webhook
	handler and from sync_all_issues/sync_issues_for_project. Without this
	one-off backfill, issues that already carried the Cycle Time Trigger Label
	before this logic existed — or on sites where the webhook never reached us —
	stay blank until their next sync. cycle_time_started_at only gets set for
	an issue once it also has a qualifying Timesheet Record logged on/after the
	label, same population the Cycle Time KPI is built from.
	"""
	if not frappe.db.exists("DocType", "GitLab Settings"):
		return

	trigger_label = frappe.db.get_single_value("GitLab Settings", "cycle_time_trigger_label")
	if not trigger_label:
		frappe.logger().info(
			"backfill_gitlab_cycle_start_label: skipped (no Cycle Time Trigger Label configured)"
		)
		return

	frappe.enqueue(
		method="phamos.gitlab_integration.gitlab_utils.backfill_cycle_start_labels",
		queue="long",
		timeout=60 * 60,
		is_async=True,
	)
	frappe.logger().info("backfill_gitlab_cycle_start_label: backfill queued")
