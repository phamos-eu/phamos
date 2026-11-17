# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab ticket references on timesheets: which issue is the child, which the parent.

A reference is an issue URL (`.../-/issues/N` or `.../-/work_items/N`), a short reference
(`group/project#N`) or a GitLab Issue name. An issue with a parent is the child and its parent
is the parent; an issue without a parent is the parent, with no child.

Lookups only use synced issues. With `fetch=True` (Stop and break), an issue of a known GitLab
Project that is not synced yet is fetched from GitLab, with its parent.
"""

import html
import re
from datetime import timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.query_builder import Order
from frappe.query_builder.functions import Lower
from frappe.utils import get_datetime, get_system_timezone, strip_html

GITLAB_REF_RE = re.compile(
	r'(?P<url>https?://[^\s"\'<>]+/-/(?:issues|work_items)/\d+)'
	r'|(?<![\w/.:#-])(?P<path>[\w.-]+(?:/[\w.-]+)+)#(?P<iid>\d+)\b'
)
_URL_PARTS_RE = re.compile(r"^(?P<project_url>https?://.+?)/-/(?:issues|work_items)/(?P<iid>\d+)/?$")


def find_gitlab_issues_in_text(*text_fields, fetch=False):
	"""(child, parent) from the first reference in the texts: the first child wins, else the first parent."""
	text = html.unescape(strip_html(" ".join(t for t in text_fields if t)))

	parent_only = None
	for match in GITLAB_REF_RE.finditer(text):
		if match.group("url"):
			issue = get_issue_by_url(match.group("url"), fetch=fetch)
		else:
			issue = get_issue_by_ref(match.group("path"), match.group("iid"), fetch=fetch)
		if not issue:
			continue
		if issue.parent_issue:
			return issue.name, issue.parent_issue
		if parent_only is None:
			parent_only = issue.name
	return None, parent_only


def resolve_reference(reference, fetch=False):
	"""(child, parent) for one reference."""
	reference = (reference or "").strip()
	if not reference:
		return None, None
	if frappe.db.exists("GitLab Issue", reference):
		parent = frappe.db.get_value("GitLab Issue", reference, "parent_issue")
		return (reference, parent) if parent else (None, reference)
	return find_gitlab_issues_in_text(reference, fetch=fetch)


def link_gitlab_issues(doc, reference=None, texts=()):
	"""Set gitlab_issue (child) and gitlab_parent_issue (parent) on a Timesheet Record.

	A given reference wins. Otherwise the texts are read, but only when nothing is linked yet,
	so an issue timer keeps its issue.
	"""
	if reference:
		child, parent = resolve_reference(reference, fetch=True)
		if child or parent:
			doc.gitlab_issue = child
			doc.gitlab_parent_issue = parent
	elif not doc.get("gitlab_issue") and not doc.get("gitlab_parent_issue"):
		child, parent = find_gitlab_issues_in_text(*texts, fetch=True)
		doc.gitlab_issue = child
		doc.gitlab_parent_issue = parent
	if doc.get("gitlab_issue") and not doc.get("gitlab_parent_issue"):
		doc.gitlab_parent_issue = frappe.db.get_value("GitLab Issue", doc.gitlab_issue, "parent_issue") or None


def issue_created_during(project, start, end, user):
	"""Newest GitLab Issue of an ERPNext project created in GitLab between start and end that is
	assigned to `user` or to nobody; a colleague's ticket is never linked.

	start / end are in the system time zone; GitLab's created_at is stored in UTC. An issue
	without created_at (fetched on the spot) counts by the time it reached ERPNext. The assignee
	matches like the panel's "My Issues": assignee_email, else gitlab_username = the local part
	of the user's email.
	"""
	if not (project and start and end and user):
		return None
	start, end = get_datetime(start), get_datetime(end)
	utc_start, utc_end = _system_to_utc(start), _system_to_utc(end)
	email = (frappe.db.get_value("User", user, "email") or "").lower()
	issue = frappe.qb.DocType("GitLab Issue")
	gitlab_project = frappe.qb.DocType("GitLab Project")
	no_email = issue.assignee_email.isnull() | (issue.assignee_email == "")
	no_username = issue.gitlab_username.isnull() | (issue.gitlab_username == "")
	mine_or_nobodys = (Lower(issue.assignee_email) == email) | (
		no_email & (no_username | (Lower(issue.gitlab_username) == email.split("@")[0]))
	)
	rows = (
		frappe.qb.from_(issue)
		.join(gitlab_project)
		.on(gitlab_project.name == issue.gitlab_project)
		.select(issue.name)
		.where(gitlab_project.frappe_project == project)
		.where(
			issue.created_at.between(utc_start, utc_end)
			| (issue.created_at.isnull() & issue.creation.between(start, end))
		)
		.where(mine_or_nobodys)
		.orderby(issue.created_at, order=Order.desc)
		.orderby(issue.creation, order=Order.desc)
		.limit(1)
	).run(pluck=True)
	return rows[0] if rows else None


def _system_to_utc(dt):
	return dt.replace(tzinfo=ZoneInfo(get_system_timezone())).astimezone(timezone.utc).replace(tzinfo=None)


def get_issue_by_url(url, fetch=False):
	name = _issue_name_by_url(url) or (fetch_issue_by_url(url) if fetch else None)
	return frappe.db.get_value("GitLab Issue", name, ["name", "parent_issue"], as_dict=True) if name else None


def get_issue_by_ref(path, iid, fetch=False):
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
	project_url = frappe.db.get_value("GitLab Project", {"namespace": path}, "web_url") if fetch else None
	return get_issue_by_url(f"{project_url.rstrip('/')}/-/issues/{iid}", fetch=True) if project_url else None


def fetch_issue_by_url(url, with_parent=True):
	"""Create the GitLab Issue for `url` from the GitLab API and return its name.

	Only for a GitLab Project we have; None when the project is unknown or GitLab fails (logged).
	"""
	parts = _URL_PARTS_RE.match(url.strip())
	project = _gitlab_project_for(parts.group("project_url")) if parts else None
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
		doc = frappe.get_doc(
			{
				"doctype": "GitLab Issue",
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
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"GitLab issue fetch failed: {url}")
		return None

	if with_parent and project.namespace:
		_link_fetched_parent(doc, project.namespace, iid)
	return doc.name


def _link_fetched_parent(doc, project_path, iid):
	"""Set the parent of a freshly fetched issue; a failure keeps the issue and is logged."""
	from phamos.gitlab_integration import gitlab_utils

	try:
		parent = gitlab_utils.get_issue_parent(project_path, iid)
		parent_url = (parent or {}).get("web_url")  # get_issue_parent renames GraphQL's webUrl
		parent_name = parent_url and (_issue_name_by_url(parent_url) or fetch_issue_by_url(parent_url, with_parent=False))
		if parent_name:
			doc.db_set("parent_issue", parent_name)
	except Exception:
		frappe.log_error(frappe.get_traceback(), f"GitLab parent fetch failed: {doc.issue_url}")


def _issue_name_by_url(url):
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
	"""Child and parent a reference will link on Stop. Reads only; never fetches or creates.

	Same gate as the Developer Action Panel: a linked Employee. Timesheet Record create is
	System Manager only, and the panel's own endpoints insert with ignore_permissions.
	"""
	if not frappe.db.exists("Employee", {"user_id": frappe.session.user}):
		frappe.throw(_("No Employee record linked to your user account."), frappe.PermissionError)
	child, parent = resolve_reference(reference)

	def describe(name):
		row = frappe.db.get_value(
			"GitLab Issue", name, ["name", "issue_id", "title", "issue_url", "gitlab_project"], as_dict=True
		)
		row.project = frappe.db.get_value("GitLab Project", row.gitlab_project, "frappe_project")
		return row

	parts = _URL_PARTS_RE.match((reference or "").strip())
	return {
		"child": describe(child) if child else None,
		"parent": describe(parent) if parent else None,
		"found": bool(child or parent),
		"fetchable": bool(not (child or parent) and parts and _gitlab_project_for(parts.group("project_url"))),
	}
