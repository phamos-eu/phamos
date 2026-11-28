"""Start the plan CI job when a GitLab issue is labelled implementation plan.

The job is .gitlab/ai_issue_plan.py. A new comment on that issue starts the
same job again so the next question does not wait for the schedule. The
pipeline is created with the Access Token on GitLab Settings. The comment
itself is posted by that job with GITLAB_API_TOKEN.
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

PLAN_LABEL = "implementation plan"


def enqueue_issue_plan(payload, labels_list, project_id):
    """Queue one pipeline when this event adds the implementation plan label."""
    try:
        if not _plan_label_added(payload, labels_list):
            return
        _enqueue_for_issue(payload, project_id)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "GitLab issue plan could not be queued")


def enqueue_plan_from_note(payload):
    """Queue one pipeline when someone replies on an implementation-plan issue."""
    try:
        attrs = payload.get("object_attributes") or {}
        if attrs.get("noteable_type") != "Issue" or attrs.get("system"):
            return
        if "phamos-ai-issue-plan" in (attrs.get("note") or ""):
            return
        issue = payload.get("issue") or {}
        if not _has_plan_label(issue.get("labels")):
            return
        _enqueue_for_issue(payload, (payload.get("project") or {}).get("id"), issue)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "GitLab issue plan could not be queued")


def trigger_plan_pipeline(project_id, issue_iid, ref):
    """Create the pipeline that runs ai_issue_plan for one issue."""
    settings = frappe.get_single("GitLab Settings")
    gitlab_url = (settings.gitlab_url or "").rstrip("/")
    token = _access_token()
    if not gitlab_url or not token:
        frappe.log_error(
            "GitLab URL or Access Token is empty, so the plan pipeline was not started.",
            "GitLab issue plan",
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
                    {"key": "AI_ISSUE_LABEL", "value": PLAN_LABEL},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        frappe.log_error(str(exc), "GitLab issue plan pipeline")
        return
    if response.status_code not in (200, 201):
        frappe.log_error(
            f"POST pipeline -> {response.status_code}\n{response.text[:1500]}",
            "GitLab issue plan pipeline",
        )


def _enqueue_for_issue(payload, project_id, issue=None):
    if not project_id or not _is_ci_project(payload, project_id):
        return
    issue = issue if issue is not None else (payload.get("object_attributes") or {})
    issue_iid = str(issue.get("iid") or "")
    ref = ((payload.get("project") or {}).get("default_branch") or "").strip()
    if not issue_iid or not ref:
        return
    frappe.enqueue(
        "phamos.gitlab_integration.issue_plan.trigger_plan_pipeline",
        queue="short",
        timeout=60,
        enqueue_after_commit=True,
        project_id=str(project_id),
        issue_iid=issue_iid,
        ref=ref,
    )


def _plan_label_added(payload, labels_list):
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
    return _has_plan_label(added)


def _has_plan_label(labels):
    for title in _label_titles(labels):
        if title.split("::")[-1].strip().lower() == PLAN_LABEL:
            return True
    return False
