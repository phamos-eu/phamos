"""Start the implement CI job when a GitLab issue is labelled plan-drafted.

The job is .gitlab/ai_issue_implement.py. The pipeline is created with the
Access Token on GitLab Settings. The merge request and the comment are
created by that job with GITLAB_API_TOKEN.
"""

from urllib.parse import quote

import frappe
import requests

from phamos.gitlab_integration.issue_analysis import (
    _access_token,
    _is_ci_project,
    _label_titles,
    _norm,
)

TRIGGER_LABEL = "plan-drafted"


def enqueue_issue_implement(payload, labels_list, project_id):
    """Queue one pipeline when this event adds the plan-drafted label."""
    try:
        if not _trigger_added(payload, labels_list):
            return
        _enqueue_for_issue(payload, project_id)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "GitLab issue implement could not be queued")


def trigger_implement_pipeline(project_id, issue_iid, ref):
    """Create the pipeline that runs ai_issue_implement for one issue."""
    settings = frappe.get_single("GitLab Settings")
    gitlab_url = (settings.gitlab_url or "").rstrip("/")
    token = _access_token()
    if not gitlab_url or not token:
        frappe.log_error(
            "GitLab URL or Access Token is empty, so the implement pipeline was not started.",
            "GitLab issue implement",
        )
        return
    try:
        response = requests.post(
            f"{gitlab_url}/api/v4/projects/{quote(str(project_id), safe='')}/pipeline",
            headers={"PRIVATE-TOKEN": token},
            json={
                "ref": ref,
                "variables": [
                    {"key": "AI_ISSUE_IID", "value": str(issue_iid)},
                    {"key": "AI_ISSUE_LABEL", "value": TRIGGER_LABEL},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        frappe.log_error(str(exc), "GitLab issue implement pipeline")
        return
    if response.status_code not in (200, 201):
        frappe.log_error(
            f"POST pipeline -> {response.status_code}\n{response.text[:1500]}",
            "GitLab issue implement pipeline",
        )


def _enqueue_for_issue(payload, project_id):
    if not project_id or not _is_ci_project(payload, project_id):
        return
    issue = payload.get("object_attributes") or {}
    issue_iid = str(issue.get("iid") or "")
    ref = ((payload.get("project") or {}).get("default_branch") or "").strip()
    if not issue_iid or not ref:
        return
    frappe.enqueue(
        "phamos.gitlab_integration.issue_implement.trigger_implement_pipeline",
        queue="short",
        timeout=60,
        enqueue_after_commit=True,
        project_id=str(project_id),
        issue_iid=issue_iid,
        ref=ref,
    )


def _trigger_added(payload, labels_list):
    action = (payload.get("object_attributes") or {}).get("action")
    if action == "open":
        added = _label_titles(labels_list)
    else:
        change = (payload.get("changes") or {}).get("labels")
        if not change:
            return False
        previous = {_norm(title) for title in _label_titles(change.get("previous"))}
        current = _label_titles(change.get("current")) or _label_titles(labels_list)
        added = [title for title in current if _norm(title) not in previous]
    return _has_trigger(added)


def _has_trigger(labels):
    for title in _label_titles(labels):
        if title.split("::")[-1].strip().lower() == TRIGGER_LABEL:
            return True
    return False
