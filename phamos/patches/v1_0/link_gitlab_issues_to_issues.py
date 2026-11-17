"""GitLab Issue records get a link to the Issue they were created from.

Before, "Create GitLab Issue" stored only the URL on the Issue (`gitlab_issue_url`). This finds the
synced GitLab Issue record for each such URL and links it. No GitLab calls: an issue that is not
synced yet stays unlinked.
"""

import frappe

from phamos.gitlab_integration.issue_refs import _issue_name_by_url


def execute():
	if not frappe.db.has_column("Issue", "gitlab_issue_url") or not frappe.db.has_column("GitLab Issue", "issue"):
		return
	for issue, url in frappe.get_all(
		"Issue", filters={"gitlab_issue_url": ["is", "set"]}, fields=["name", "gitlab_issue_url"], as_list=True
	):
		record = _issue_name_by_url(url.strip())
		if record and not frappe.db.get_value("GitLab Issue", record, "issue"):
			frappe.db.set_value("GitLab Issue", record, "issue", issue, update_modified=False)
