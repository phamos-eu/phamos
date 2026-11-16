"""Start the issue-analysis CI job when a GitLab issue is labelled bug or question.

GitLab does not start a pipeline on a label change. The issue webhook does,
for the project in Phriend Settings (the project whose CI/CD variables already
hold ANTHROPIC_API_KEY and GITLAB_API_TOKEN for the MR review). The job is
.gitlab/ai_issue_analysis.py. The pipeline is created with the Access Token
on GitLab Settings; the comment itself is posted by that job with
GITLAB_API_TOKEN.
"""

from urllib.parse import quote

import frappe
import requests
from frappe.utils.password import get_decrypted_password

ANALYSIS_LABELS = ("bug", "question")


def enqueue_issue_analysis(payload, labels_list, project_id):
    """Queue one pipeline per newly added bug or question label."""
    try:
        kinds = newly_added_analysis_labels(payload, labels_list)
        if not kinds or not project_id or not _is_ci_project(payload, project_id):
            return
        issue_iid = str((payload.get("object_attributes") or {}).get("iid") or "")
        ref = ((payload.get("project") or {}).get("default_branch") or "").strip()
        if not issue_iid or not ref:
            return
        for kind in kinds:
            frappe.enqueue(
                "phamos.gitlab_integration.issue_analysis.trigger_analysis_pipeline",
                queue="short",
                timeout=60,
                enqueue_after_commit=True,
                project_id=str(project_id),
                issue_iid=issue_iid,
                label=kind,
                ref=ref,
            )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "GitLab issue analysis could not be queued")


def trigger_analysis_pipeline(project_id, issue_iid, label, ref):
    """Create the pipeline that runs ai_issue_analysis with the CI/CD variables."""
    if label not in ANALYSIS_LABELS:
        return
    settings = frappe.get_single("GitLab Settings")
    gitlab_url = (settings.gitlab_url or "").rstrip("/")
    token = _access_token()
    if not gitlab_url or not token:
        frappe.log_error(
            "GitLab URL or Access Token is empty, so the analysis pipeline was not started.",
            "GitLab issue analysis",
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
                    {"key": "AI_ISSUE_LABEL", "value": label},
                ],
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        frappe.log_error(str(exc), "GitLab issue analysis pipeline")
        return
    if response.status_code not in (200, 201):
        frappe.log_error(
            f"POST pipeline -> {response.status_code}\n{response.text[:1500]}",
            "GitLab issue analysis pipeline",
        )


def newly_added_analysis_labels(payload, labels_list):
    """bug and question labels this event added. Empty when labels did not change."""
    action = (payload.get("object_attributes") or {}).get("action")
    if action == "open":
        added = _label_titles(labels_list)
    else:
        change = (payload.get("changes") or {}).get("labels")
        if not change:
            return []
        previous = {_norm(title) for title in _label_titles(change.get("previous"))}
        current = _label_titles(change.get("current")) or _label_titles(labels_list)
        added = [title for title in current if _norm(title) not in previous]

    kinds = []
    for title in added:
        kind = analysis_label(title)
        if kind and kind not in kinds:
            kinds.append(kind)
    return kinds


def analysis_label(title):
    """Return bug or question when the label is that word, including type::bug."""
    leaf = (title or "").split("::")[-1].strip().lower()
    if leaf in ANALYSIS_LABELS:
        return leaf
    return None


def _is_ci_project(payload, project_id):
    """The MR-review variables live on one project: Phriend Settings' GitLab project."""
    try:
        configured = (frappe.db.get_single_value("Phriend Settings", "gitlab_project") or "").strip().strip("/")
    except Exception:
        return False
    if not configured:
        return False
    if configured.isdigit():
        return str(project_id) == configured
    path = ((payload.get("project") or {}).get("path_with_namespace") or "").strip().strip("/")
    return path.lower() == configured.lower()


def _label_titles(labels):
    titles = []
    for label in labels or []:
        if isinstance(label, str):
            title = label
        elif isinstance(label, dict):
            title = label.get("title") or label.get("name") or ""
        else:
            continue
        title = title.strip()
        if title:
            titles.append(title)
    return titles


def _norm(title):
    return title.strip().lower()


def _access_token():
    try:
        return get_decrypted_password(
            "GitLab Settings", "GitLab Settings", "access_token", raise_exception=False
        ) or None
    except Exception:
        return None
