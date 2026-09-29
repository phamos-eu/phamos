# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, today

from phamos.gitlab_integration.gitlab_utils import (
	_parse_gitlab_datetime,
	get_label_events_for_project_issue,
)

LEDGER_DOCTYPE = "GitLab Issue Label Ledger"


def _build_label_intervals(events):
	"""Turn GitLab's raw add/remove events into one interval per time a label
	was on the issue: {gitlab_event_id, label, added_at, added_by, removed_at, removed_by}."""
	events = sorted(
		(e for e in events if (e.get("label") or {}).get("name")),
		key=lambda e: (e.get("created_at") or "", e.get("id") or 0),
	)

	open_intervals = {}
	intervals = []
	for event in events:
		label = event["label"]["name"]
		username = (event.get("user") or {}).get("username") or ""
		event_time = _parse_gitlab_datetime(event.get("created_at"))

		if event.get("action") == "add":
			# A second "add" while the label is still on the issue changes nothing
			if label in open_intervals:
				continue
			interval = {
				"gitlab_event_id": str(event["id"]),
				"label": label,
				"added_at": event_time,
				"added_by": username,
				"removed_at": None,
				"removed_by": "",
			}
			open_intervals[label] = interval
			intervals.append(interval)

		elif event.get("action") == "remove":
			interval = open_intervals.pop(label, None)
			if interval:
				interval["removed_at"] = event_time
				interval["removed_by"] = username

	return intervals


def sync_issue_label_ledger(issue_doc_name, source="Sync"):
	"""Bring one issue's ledger in line with GitLab's full label event history."""
	issue = frappe.db.get_value(
		"GitLab Issue", issue_doc_name, ["issue_id", "gitlab_project"], as_dict=True
	)
	if not issue:
		return 0

	project_id = frappe.db.get_value("GitLab Project", issue.gitlab_project, "project_id")
	if not project_id:
		return 0

	intervals = _build_label_intervals(
		get_label_events_for_project_issue(project_id, issue.issue_id)
	)

	existing = {
		row.gitlab_event_id: row
		for row in frappe.get_all(
			LEDGER_DOCTYPE,
			filters={"gitlab_issue": issue_doc_name},
			fields=["name", "gitlab_event_id", "label", "added_at", "removed_at", "removed_by"],
		)
	}

	changed = 0
	for interval in intervals:
		row = existing.get(interval["gitlab_event_id"])
		if row:
			if row.removed_at != interval["removed_at"] or (row.removed_by or "") != interval["removed_by"]:
				frappe.db.set_value(
					LEDGER_DOCTYPE,
					row.name,
					{"removed_at": interval["removed_at"], "removed_by": interval["removed_by"]},
				)
				changed += 1
			continue

		try:
			frappe.get_doc(
				{
					"doctype": LEDGER_DOCTYPE,
					"gitlab_issue": issue_doc_name,
					"gitlab_project": issue.gitlab_project,
					"source": source,
					**interval,
				}
			).insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			# Backfill and a sync job filled the same event at the same time
			continue
		changed += 1

	return changed


def label_ledger_needs_sync(issue_doc_name, current_labels, recently_updated=False):
	"""Regular-sync safety net for missed webhooks, decided without calling GitLab.

	- Touched recently: always re-sync, since a label added and removed in
	  between leaves the current labels looking unchanged.
	- No ledger rows yet: left to the backfill, otherwise the first sync after
	  deploy calls GitLab for every labelled issue and runs past its timeout.
	- Otherwise: re-sync only when the open ledger labels differ from GitLab's."""
	if recently_updated:
		return True

	open_labels = frappe.get_all(
		LEDGER_DOCTYPE,
		filters={"gitlab_issue": issue_doc_name, "removed_at": ["is", "not set"]},
		pluck="label",
	)
	if not open_labels and not frappe.db.exists(LEDGER_DOCTYPE, {"gitlab_issue": issue_doc_name}):
		return False

	return set(open_labels) != set(filter(None, current_labels))


def sync_issue_label_ledger_job(issue_doc_name, source="Webhook"):
	sync_issue_label_ledger(issue_doc_name, source=source)
	frappe.db.commit()


def enqueue_issue_label_ledger_sync(issue_doc_name, source="Webhook"):
	frappe.enqueue(
		"phamos.gitlab_integration.label_ledger.sync_issue_label_ledger_job",
		queue="short",
		job_id=f"label_ledger::{issue_doc_name}",
		deduplicate=True,
		enqueue_after_commit=True,
		issue_doc_name=issue_doc_name,
		source=source,
	)


def delete_issue_label_ledger(doc, method=None):
	"""GitLab Issue on_trash — the ledger links to the issue, so its rows have
	to go first or deleting the issue (e.g. from the delete webhook) fails."""
	frappe.db.delete(LEDGER_DOCTYPE, {"gitlab_issue": doc.name})


def _default_backfill_since():
	"""1 January of last year."""
	return getdate(today()).replace(year=getdate(today()).year - 1, month=1, day=1)


def backfill_label_ledger(project_name=None, limit=None, since=None):
	"""One-off historical fill of the ledger for every issue still open, or
	closed on/after `since` (defaults to 1 January of last year)."""
	since = getdate(since) if since else _default_backfill_since()
	filters = {"gitlab_project": project_name} if project_name else {}
	issues = frappe.get_all(
		"GitLab Issue",
		filters=filters,
		or_filters=[["closed_at", "is", "not set"], ["closed_at", ">=", since]],
		pluck="name",
		limit_page_length=int(limit) if limit else None,
	)

	synced = 0
	for issue_doc_name in issues:
		try:
			if sync_issue_label_ledger(issue_doc_name, source="Backfill"):
				synced += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Label Ledger Backfill Failed - {issue_doc_name}")

		frappe.db.commit()

	return f"Label history filled for {synced} of {len(issues)} issues"


def _backfill_label_ledger_and_notify(project_name, notify_user):
	result = backfill_label_ledger(project_name)
	frappe.publish_realtime(event="show_alert", message=f"✅ {result}", user=notify_user)


@frappe.whitelist()
def backfill_label_ledger_background(project_name=None):
	frappe.only_for("System Manager")
	frappe.enqueue(
		"phamos.gitlab_integration.label_ledger._backfill_label_ledger_and_notify",
		queue="long",
		timeout=4 * 60 * 60,
		job_id="label_ledger_backfill",
		deduplicate=True,
		project_name=project_name,
		notify_user=frappe.session.user,
	)
	return {"status": "queued", "message": "Label history backfill queued as background job"}
