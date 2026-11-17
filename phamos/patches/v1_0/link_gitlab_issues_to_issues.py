"""GitLab Issue records get a link to the Issue they were created from.

Before, "Create GitLab Issue" stored only the URL on the Issue (`gitlab_issue_url`). This finds the
synced GitLab Issue record for each such URL and links it. No GitLab calls: an issue that is not
synced yet stays unlinked.
"""

import frappe


def execute():
	if not frappe.db.has_column("Issue", "gitlab_issue_url") or not frappe.db.has_column("GitLab Issue", "issue"):
		return
	for issue, url in frappe.get_all(
		"Issue", filters={"gitlab_issue_url": ["is", "set"]}, fields=["name", "gitlab_issue_url"], as_list=True
	):
		record = _issue_name_by_url(url.strip())
		if record and not frappe.db.get_value("GitLab Issue", record, "issue"):
			frappe.db.set_value("GitLab Issue", record, "issue", issue, update_modified=False)


def _issue_name_by_url(url):
	# version-15 has no phamos.gitlab_integration.issue_refs (develop only): the same lookup.
	# GitLab answers with /-/issues/ or /-/work_items/ for the same issue.
	variants = [url, url.replace("/-/work_items/", "/-/issues/"), url.replace("/-/issues/", "/-/work_items/")]
	return frappe.db.get_value("GitLab Issue", {"issue_url": ["in", list(dict.fromkeys(variants))]}, "name")
