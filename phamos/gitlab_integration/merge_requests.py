# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab merge requests (#1977): synced every 2 hours and by webhook, for the Team Cockpit.

- The first run of a project fetches the merge requests updated in the last 24 months; later runs
  fetch what changed since `GitLab Project.merge_requests_synced_at`. Merge requests come oldest
  change first and each is committed on its own, with `merge_requests_synced_at` moved to its
  update time: a run that is stopped or fails on one merge request goes on from there next time.
- The sync runs as its own background job, so it never shares the issue sync's time limit.
- Lines added and removed come from the merge request's diffs, counted per file, leaving out the
  paths in GitLab Settings ("Paths left out of line counts": lock files, built assets, translation
  files). They are taken again only when the merge request's head changes.
- Times are stored as GitLab sends them, in UTC, as for GitLab Issues.
- The author's email comes from `gitlab_utils.get_user_email` (public email, or the primary email
  with an admin token); the Team Cockpit matches it to Employees (#1976, #2227).
"""

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import frappe
import requests
from frappe.utils import add_months, get_system_timezone, now_datetime

from phamos.gitlab_integration.gitlab_utils import _parse_gitlab_datetime, get_gitlab_headers, get_user_email

FIRST_SYNC_MONTHS = 24
DEFAULT_EXCLUSIONS = (
	"yarn.lock",
	"package-lock.json",
	"poetry.lock",
	"*/public/dist/*",
	"public/dist/*",
	"*/public/*/assets/*",
	"*.min.js",
	"*.map",
	"*.csv",
	"*.po",
)


def _api(path):
	return f"{frappe.db.get_single_value('GitLab Settings', 'gitlab_url')}/api/v4/{path}"


def _get_all(path, params=None):
	"""Every page of a GitLab list endpoint."""
	rows, page = [], 1
	while True:
		response = requests.get(
			_api(path), headers=get_gitlab_headers(), params={**(params or {}), "per_page": 100, "page": page}, timeout=30
		)
		response.raise_for_status()
		batch = response.json()
		if not batch:
			return rows
		rows.extend(batch)
		if len(batch) < 100:
			return rows
		page += 1


# --- line counts ---------------------------------------------------------------------------------


def exclusion_patterns():
	"""The patterns from GitLab Settings, one per line; the defaults while the field is empty."""
	text = frappe.db.get_single_value("GitLab Settings", "merge_request_line_exclusions")
	patterns = [line.strip() for line in (text or "").splitlines() if line.strip()]
	return patterns or list(DEFAULT_EXCLUSIONS)


def _pattern_regex(pattern):
	# "*" matches any characters, also "/"; a pattern without "/" matches the file name anywhere;
	# a trailing "/" means everything in that folder
	if pattern.endswith("/"):
		pattern += "*"
	body = re.escape(pattern).replace(r"\*", ".*")
	return re.compile(rf"(.*/)?{body}$" if "/" not in pattern else rf"{body}$")


def is_excluded(path, patterns):
	return any(_pattern_regex(p).match(path or "") for p in patterns)


def count_lines(diffs, patterns):
	"""(added, removed, files) over the diffs of the files not excluded."""
	added = removed = files = 0
	for diff in diffs:
		path = diff.get("new_path") or diff.get("old_path")
		if is_excluded(path, patterns):
			continue
		files += 1
		# GitLab's per-file diff text has no "+++"/"---" file headers: every line starting with "+"
		# or "-" is a code line ("-- comment", "---" in YAML, "++i" included)
		for line in (diff.get("diff") or "").splitlines():
			if line.startswith("+"):
				added += 1
			elif line.startswith("-"):
				removed += 1
	return added, removed, files


def _diffs(project_id, iid):
	"""The files of a merge request with their diff text (GitLab 15.7+ `/diffs`, else `/changes`)."""
	try:
		return _get_all(f"projects/{project_id}/merge_requests/{iid}/diffs")
	except requests.HTTPError as e:
		if e.response is None or e.response.status_code != 404:
			raise
	response = requests.get(
		_api(f"projects/{project_id}/merge_requests/{iid}/changes"), headers=get_gitlab_headers(), timeout=60
	)
	response.raise_for_status()
	return response.json().get("changes") or []


# --- upsert --------------------------------------------------------------------------------------


def _linked_issues(project_id, iid):
	"""GitLab Issue names of the issues this merge request closes, where they are synced."""
	names = []
	try:
		closes = _get_all(f"projects/{project_id}/merge_requests/{iid}/closes_issues")
	except requests.RequestException:
		return names
	for issue in closes:
		name = frappe.db.get_value(
			"GitLab Issue", {"gitlab_project": str(issue.get("project_id")), "issue_id": str(issue.get("iid"))}, "name"
		)
		if name:
			names.append(name)
	return names


def upsert_merge_request(project, mr, patterns=None):
	"""Create or update the GitLab Merge Request for `mr` (GitLab API JSON) of GitLab Project
	`project` (its name, which is the GitLab project id). Returns the record's name."""
	patterns = patterns if patterns is not None else exclusion_patterns()
	try:
		return _upsert(project, mr, patterns)
	except frappe.DuplicateEntryError:
		# the webhook and the sync created it at the same time: update the one that won
		frappe.db.rollback(save_point="merge_request_upsert")
		return _upsert(project, mr, patterns)


def _upsert(project, mr, patterns):
	frappe.db.savepoint("merge_request_upsert")
	name = frappe.db.get_value("GitLab Merge Request", {"gitlab_project": project, "iid": mr["iid"]}, "name")
	doc = frappe.get_doc("GitLab Merge Request", name) if name else frappe.new_doc("GitLab Merge Request")
	author = mr.get("author") or {}
	doc.update(
		{
			"gitlab_project": project,
			"iid": mr["iid"],
			"title": (mr.get("title") or "")[:140],
			"web_url": mr.get("web_url"),
			"state": mr.get("state"),
			"author_username": author.get("username"),
			"source_branch": mr.get("source_branch"),
			"target_branch": mr.get("target_branch"),
			"created_at": _parse_gitlab_datetime(mr.get("created_at")),
			"merged_at": _parse_gitlab_datetime(mr.get("merged_at")),
			"closed_at": _parse_gitlab_datetime(mr.get("closed_at")),
		}
	)
	if author.get("id") and not doc.author_email:
		doc.author_email = get_user_email(author["id"]) or None
	head = mr.get("sha")
	if head and head != doc.sha:
		diffs = _diffs(project, mr["iid"])
		doc.lines_added, doc.lines_removed, doc.files_changed = count_lines(diffs, patterns)
		doc.set("issues", [{"gitlab_issue": issue} for issue in _linked_issues(project, mr["iid"])])
		# GitLab builds the diffs after a push: an empty answer may just be early, so the head is
		# only remembered once there were diffs, and the next sync counts again
		if diffs:
			doc.sha = head
	doc.flags.ignore_links = True
	doc.save(ignore_permissions=True)
	return doc.name


# --- sync ----------------------------------------------------------------------------------------


def sync_project_merge_requests(project):
	"""One GitLab Project: merge requests updated since its last run (the first run: 24 months),
	oldest change first. Each is committed on its own and moves `merge_requests_synced_at` to its
	update time. On the first one that fails the project stops, so that one is fetched again next
	time; nothing after it is skipped for good."""
	synced_at = frappe.db.get_value("GitLab Project", project, "merge_requests_synced_at")
	since = synced_at or add_months(now_datetime(), -FIRST_SYNC_MONTHS)
	patterns = exclusion_patterns()
	count = 0
	for mr in _get_all(
		f"projects/{project}/merge_requests",
		{"state": "all", "scope": "all", "updated_after": _iso_utc(since), "order_by": "updated_at", "sort": "asc"},
	):
		try:
			upsert_merge_request(project, mr, patterns)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"GitLab merge request {project}!{mr.get('iid')} not synced")
			break
		updated = _parse_gitlab_datetime(mr.get("updated_at"))
		if updated:
			frappe.db.set_value(
				"GitLab Project", project, "merge_requests_synced_at", _utc_to_system(updated), update_modified=False
			)
		frappe.db.commit()
		count += 1
	return count


def _utc_to_system(value):
	"""A naive UTC datetime (as the sync stores GitLab times) in naive system time."""
	return value.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


def _iso_utc(value):
	"""A system-time datetime as the ISO UTC string GitLab expects for updated_after."""
	from phamos.gitlab_integration.issue_refs import _system_to_utc

	value = value if isinstance(value, datetime) else datetime.combine(value, datetime.min.time())
	return _system_to_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def sync_all_merge_requests_background():
	"""Queued by gitlab_utils.sync_gitlab_data: its own job with its own time limit."""
	frappe.enqueue(
		"phamos.gitlab_integration.merge_requests.sync_all_merge_requests",
		queue="long",
		timeout=60 * 60,
		job_id="gitlab_merge_request_sync",
		deduplicate=True,
	)


def sync_all_merge_requests():
	"""Every GitLab Project; a failing project is logged and skipped."""
	total = 0
	for project in frappe.get_all("GitLab Project", pluck="name"):
		try:
			total += sync_project_merge_requests(project)
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"GitLab merge requests of project {project} not synced")
	return total


def handle_merge_request_webhook(payload):
	"""A "Merge Request Hook": queue the update and answer GitLab right away (its webhook timeout is
	short, and timeouts count towards disabling the whole hook)."""
	project_id = str((payload.get("project") or {}).get("id") or "")
	iid = (payload.get("object_attributes") or {}).get("iid")
	if not project_id or not iid or not frappe.db.exists("GitLab Project", project_id):
		return
	frappe.enqueue(
		"phamos.gitlab_integration.merge_requests.update_merge_request",
		project_id=project_id,
		iid=iid,
		job_id=f"gitlab_merge_request_{project_id}_{iid}",
		deduplicate=True,
		enqueue_after_commit=True,
	)


def update_merge_request(project_id, iid):
	"""Fetch one merge request and update it (webhook job)."""
	response = requests.get(_api(f"projects/{project_id}/merge_requests/{iid}"), headers=get_gitlab_headers(), timeout=30)
	response.raise_for_status()
	upsert_merge_request(project_id, response.json())
