# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab ticket references on timesheets: which issue is the child, which the parent (#1862).

One place for every panel (Project Action Panel, Developer Action Panel, Personal Cockpit,
customer comments). A reference is a full issue URL (`.../-/issues/N` or `.../-/work_items/N`),
a short reference (`group/project#N`) or a GitLab Issue docname.

Rule: the issue has a parent → it is the child, its parent is the parent. The issue has no
parent → it is the parent and there is no child.

A URL whose issue is not synced yet is fetched from GitLab on the spot (the issue and its
parent), as long as it belongs to a GitLab Project we already have.
"""

import html
import re

import frappe
from frappe.utils import strip_html

# Full GitLab issue URL, or a short reference like "suncycle/suncycle#2494".
GITLAB_REF_RE = re.compile(
	r'(?P<url>https?://[^\s"\'<>]+/-/(?:issues|work_items)/\d+)'
	r'|(?<![\w/.:#-])(?P<path>[\w.-]+(?:/[\w.-]+)+)#(?P<iid>\d+)\b'
)
_URL_PARTS_RE = re.compile(r"^(?P<project_url>https?://.+?)/-/(?:issues|work_items)/(?P<iid>\d+)/?$")


def find_gitlab_issues_in_text(*text_fields):
	"""Scan text for GitLab references and return (child_issue_name, parent_issue_name).

	The first child found wins; otherwise the first parent found. References that cannot be
	matched to a GitLab Issue (not synced and not fetchable) are ignored.
	"""
	text = " ".join(t for t in text_fields if t)
	text = html.unescape(strip_html(text))

	parent_only = None
	for match in GITLAB_REF_RE.finditer(text):
		if match.group("url"):
			issue = get_issue_by_url(match.group("url"))
		else:
			issue = get_issue_by_ref(match.group("path"), match.group("iid"))
		if not issue:
			continue
		if issue.parent_issue:
			return issue.name, issue.parent_issue
		if parent_only is None:
			parent_only = issue.name
	return None, parent_only


def child_and_parent(issue_name):
	"""(child, parent) for one GitLab Issue docname, by the rule above."""
	parent = frappe.db.get_value("GitLab Issue", issue_name, "parent_issue")
	return (issue_name, parent) if parent else (None, issue_name)


def resolve_reference(reference):
	"""(child, parent) for one reference: a GitLab Issue docname, a URL or group/project#N."""
	reference = (reference or "").strip()
	if not reference:
		return None, None
	if frappe.db.exists("GitLab Issue", reference):
		return child_and_parent(reference)
	return find_gitlab_issues_in_text(reference)


def link_gitlab_issues(doc, reference=None, texts=()):
	"""Set doc.gitlab_issue (child) and doc.gitlab_parent_issue (parent) on a Timesheet Record.

	An explicit `reference` (picked ticket or pasted URL) wins. Otherwise, when nothing is linked
	yet, the texts (goal, result) are scanned. A child without a parent gets its parent filled in.
	"""
	if reference:
		child, parent = resolve_reference(reference)
		if child or parent:
			doc.gitlab_issue = child
			doc.gitlab_parent_issue = parent
	elif not doc.get("gitlab_issue") and not doc.get("gitlab_parent_issue"):
		child, parent = find_gitlab_issues_in_text(*texts)
		if child:
			doc.gitlab_issue = child
		if parent:
			doc.gitlab_parent_issue = parent
	if doc.get("gitlab_issue") and not doc.get("gitlab_parent_issue"):
		doc.gitlab_parent_issue = frappe.db.get_value("GitLab Issue", doc.gitlab_issue, "parent_issue") or None


def get_issue_by_url(url):
	"""GitLab Issue for a URL (either the /-/issues/ or the /-/work_items/ form); fetched if not synced."""
	variants = [url, url.replace("/-/work_items/", "/-/issues/"), url.replace("/-/issues/", "/-/work_items/")]
	issue = frappe.db.get_value(
		"GitLab Issue",
		{"issue_url": ["in", list(dict.fromkeys(variants))]},
		["name", "parent_issue"],
		as_dict=True,
	)
	if issue:
		return issue
	name = fetch_issue_by_url(url)
	return frappe.db.get_value("GitLab Issue", name, ["name", "parent_issue"], as_dict=True) if name else None


def get_issue_by_ref(path, iid):
	"""GitLab Issue for a short reference (group/project#N), by the end of its URL."""
	escaped = path.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
	issues = frappe.get_all(
		"GitLab Issue",
		or_filters=[
			["issue_url", "like", f"%/{escaped}/-/work_items/{iid}"],
			["issue_url", "like", f"%/{escaped}/-/issues/{iid}"],
		],
		fields=["name", "parent_issue"],
		limit=1,
	)
	if issues:
		return issues[0]
	project_url = frappe.db.get_value("GitLab Project", {"namespace": path}, "web_url")
	if not project_url:
		return None
	return get_issue_by_url(f"{project_url.rstrip('/')}/-/issues/{iid}")


def fetch_issue_by_url(url, _depth=0):
	"""Create the GitLab Issue for `url` from the GitLab API, with its parent; return its name.

	Only for issues of a GitLab Project we already have. Returns None when the project is
	unknown or GitLab can't be reached; the error is logged, the caller just doesn't link.
	"""
	parts = _URL_PARTS_RE.match(url.strip())
	if not parts:
		return None
	project = _gitlab_project_for(parts.group("project_url"))
	if not project:
		return None
	iid = parts.group("iid")
	existing = frappe.db.get_value("GitLab Issue", {"gitlab_project": project.name, "issue_id": iid}, "name")
	if existing:
		return existing

	from phamos.gitlab_integration import gitlab_utils

	try:
		data = gitlab_utils.get_issue_for_project(project.project_id, iid)
		assignee = data.get("assignee") or {}
		doc = frappe.new_doc("GitLab Issue")
		doc.update(
			{
				"issue_id": str(data["iid"]),
				"gitlab_project": project.name,
				"title": data.get("title") or "",
				"state": data.get("state"),
				"due_date": data.get("due_date") or None,
				"assignee": assignee.get("name", ""),
				"gitlab_username": assignee.get("username", ""),
				"issue_url": data.get("web_url") or url,
				"labels": ", ".join(data.get("labels") or []),
			}
		)
		doc.insert(ignore_permissions=True)

		parent = gitlab_utils.get_issue_parent(project.namespace, iid) if project.namespace else None
		if parent and parent.get("webUrl") and _depth == 0:
			parent_name = (get_issue_by_url_local(parent["webUrl"]) or fetch_issue_by_url(parent["webUrl"], _depth=1))
			if parent_name:
				doc.db_set("parent_issue", parent_name)
		return doc.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"GitLab issue fetch failed: {url}")
		return None


def get_issue_by_url_local(url):
	"""Name of the synced GitLab Issue for `url`, without fetching."""
	variants = [url, url.replace("/-/work_items/", "/-/issues/"), url.replace("/-/issues/", "/-/work_items/")]
	return frappe.db.get_value("GitLab Issue", {"issue_url": ["in", list(dict.fromkeys(variants))]}, "name")


def _gitlab_project_for(project_url):
	project_url = project_url.rstrip("/")
	return frappe.db.get_value(
		"GitLab Project",
		{"web_url": ["in", [project_url, project_url + "/"]]},
		["name", "project_id", "namespace"],
		as_dict=True,
	)


@frappe.whitelist()
def preview_reference(reference):
	"""What a ticket reference links to, for the Stop panels: child and parent with id and title."""
	child, parent = resolve_reference(reference)

	def describe(name):
		if not name:
			return None
		row = frappe.db.get_value(
			"GitLab Issue", name, ["name", "issue_id", "title", "issue_url", "gitlab_project"], as_dict=True
		)
		if row:
			row["project"] = frappe.db.get_value("GitLab Project", row.gitlab_project, "frappe_project")
		return row

	return {"child": describe(child), "parent": describe(parent), "found": bool(child or parent)}
