import frappe


def execute():
	"""Queue one full GitLab sync after deploy so existing issues get refreshed."""
	if not frappe.db.exists("DocType", "GitLab Settings"):
		return

	settings = frappe.get_single("GitLab Settings")
	if not settings.gitlab_url:
		frappe.logger().info("queue_gitlab_full_sync_after_deploy: skipped (GitLab URL not configured)")
		return

	frappe.enqueue(
		method="phamos.gitlab_integration.gitlab_utils.sync_gitlab_data",
		queue="long",
		timeout=60 * 60,
		is_async=True,
	)
	frappe.logger().info("queue_gitlab_full_sync_after_deploy: full GitLab sync queued")