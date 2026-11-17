# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The GitLab issues of an Issue: one Issue can hold several, each a linked GitLab Issue record.

"Create GitLab Issue" (phamos.phriend.api.create_gitlab_issue) creates the record right away from
GitLab's answer, so the Issue shows it at once; the webhook and the sync keep it up to date and
never touch its `issue` link.
"""

import frappe
from frappe.utils import cstr

GITLAB_ISSUE = "GitLab Issue"
ROW_FIELDS = ["name", "issue_id", "title", "state", "labels", "issue_url", "gitlab_project", "assignee", "creation"]


def link_created(issue, data):
	"""The GitLab Issue record for an issue GitLab just created (`data`, its API answer), linked to
	`issue`. Returns the record's name, or None when the GitLab Project is not in ERPNext yet.

	The webhook for the new issue can be faster than this: then its record gets the link.
	"""
	project = frappe.db.get_value("GitLab Project", {"project_id": cstr(data.get("project_id"))}, "name")
	if not project:
		frappe.log_error(
			title="Phriend: GitLab project not synced",
			message=(
				f"GitLab project {data.get('project_id')} is not a GitLab Project in ERPNext, so "
				f"{data.get('web_url')} is not linked to Issue {issue} as a record. "
				"Run Sync Projects in GitLab Settings."
			),
		)
		return None

	key = {"gitlab_project": project, "issue_id": cstr(data.get("iid"))}
	name = frappe.db.get_value(GITLAB_ISSUE, key, "name")
	if not name:
		name = _insert(issue, key, data)
	if name:
		frappe.db.set_value(GITLAB_ISSUE, name, "issue", issue, update_modified=False)
	return name


def _insert(issue, key, data):
	from phamos.gitlab_integration.gitlab_utils import _get_issue_timestamp_fields, _normalize_issue_text

	assignee = (data.get("assignees") or [{}])[0] or {}
	doc = frappe.get_doc(
		{
			"doctype": GITLAB_ISSUE,
			**key,
			"issue": issue,
			"title": _normalize_issue_text(data.get("title")),
			"description": _normalize_issue_text(data.get("description")),
			"state": data.get("state") or "opened",
			"issue_url": data.get("web_url") or "",
			"labels": ", ".join(data.get("labels") or []),
			"assignee": assignee.get("name", ""),
			"gitlab_username": assignee.get("username", ""),
			**_get_issue_timestamp_fields(data),
		}
	)
	# A duplicate key leaves the rest of the request's work alone: roll back to here only.
	frappe.db.savepoint("phriend_gitlab_issue")
	try:
		doc.insert(ignore_permissions=True)
		return doc.name
	except frappe.DuplicateEntryError:
		frappe.db.rollback(save_point="phriend_gitlab_issue")
		return frappe.db.get_value(GITLAB_ISSUE, key, "name")


def issue_gitlab_issues(issue):
	"""The GitLab issues linked to an Issue, oldest first, as the Issue page lists them.

	The caller has checked that the user may read the Issue; the rows say no more than the
	GitLab issue itself (title, state, labels) and are read without GitLab Issue permission,
	which only System Managers have.
	"""
	rows = frappe.get_all(
		GITLAB_ISSUE, filters={"issue": issue}, fields=ROW_FIELDS, order_by="creation asc"
	)
	namespaces = {}
	for row in rows:
		if row.gitlab_project not in namespaces:
			namespaces[row.gitlab_project] = (
				frappe.db.get_value("GitLab Project", row.gitlab_project, "namespace") or ""
			)
	return [
		{
			"name": row.name,
			"reference": f"{namespaces[row.gitlab_project]}#{row.issue_id}"
			if namespaces[row.gitlab_project]
			else f"#{row.issue_id}",
			"title": row.title or "",
			"state": row.state or "",
			"labels": [label.strip() for label in cstr(row.labels).split(",") if label.strip()],
			"url": row.issue_url or "",
			"assignee": row.assignee or "",
		}
		for row in rows
	]


@frappe.whitelist()
def get_issue_gitlab(issue):
	"""The GitLab issues of an Issue the user may read, for the block on the Desk form."""
	frappe.get_doc("Issue", issue).check_permission("read")
	return issue_gitlab_issues(issue)

