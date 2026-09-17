#!/usr/bin/env python3
"""Fetches an MR diff from GitLab and posts a Claude-generated review as an MR comment.
Invoked by .gitlab-ci.yml's ai_code_review job.
"""

import os
import sys
import urllib.request
import urllib.error
import json

MARKER = "<!-- ai-code-review:phamos -->"

MAX_DIFF_CHARS = int(os.environ.get("AI_REVIEW_MAX_DIFF_CHARS", "60000"))
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")

SKIP_EXTENSIONS = (
    ".lock", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
    ".ttf", ".eot", ".ico", ".pdf", ".min.js", ".min.css",
)
SKIP_PATHS = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml")


def env(name, required=True):
    val = os.environ.get(name)
    if required and not val:
        print(f"Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return val


def gitlab_request(method, url, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("PRIVATE-TOKEN", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        print(f"GitLab API error ({method} {url}): {e.code} {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


def build_diff_text(changes):
    parts = []
    total = 0
    truncated = False
    for change in changes:
        path = change.get("new_path") or change.get("old_path") or ""
        if path.endswith(SKIP_EXTENSIONS) or os.path.basename(path) in SKIP_PATHS:
            continue
        diff = change.get("diff", "")
        if not diff:
            continue
        chunk = f"--- {path} ---\n{diff}\n"
        if total + len(chunk) > MAX_DIFF_CHARS:
            truncated = True
            break
        parts.append(chunk)
        total += len(chunk)
    text = "\n".join(parts)
    if truncated:
        text += "\n\n[diff truncated for length]"
    return text


def call_claude(api_key, diff_text, mr_title, mr_description):
    prompt = f"""You are reviewing a merge request for a Frappe/ERPNext custom app called "phamos" \
(Python backend + Vue/JS frontends), targeting the version-15 branch.

MR title: {mr_title}
MR description: {mr_description or "(none)"}

Review the diff below for:
- Correctness bugs and logic errors
- Frappe/ERPNext-specific pitfalls (permissions, doctype validation, whitelisted methods, \
  SQL injection via frappe.db.sql, migration/patch safety)
- Security issues (OWASP top 10, especially injection and access control)
- Obvious reuse/simplification opportunities

Do not comment on formatting/style that a linter would catch. Be concise. If you find no issues, \
say so briefly. Structure findings as a short markdown list, each with file reference, the issue, \
and a suggested fix. Skip preamble.

Diff:
{diff_text}
"""

    payload = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=data, method="POST"
    )
    req.add_header("x-api-key", api_key)
    req.add_header("anthropic-version", "2023-06-01")
    req.add_header("content-type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Anthropic API error: {e.code} {e.read().decode()}", file=sys.stderr)
        sys.exit(1)

    return "".join(block.get("text", "") for block in result.get("content", []))


def upsert_note(server_url, project_id, mr_iid, token, body):
    notes_url = f"{server_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
    notes = gitlab_request("GET", notes_url + "?per_page=100", token) or []
    existing = next((n for n in notes if MARKER in n.get("body", "")), None)

    full_body = f"{MARKER}\n### 🤖 Claude code review\n\n{body}"

    if existing:
        upsert_url = f"{notes_url}/{existing['id']}"
        gitlab_request("PUT", upsert_url, token, {"body": full_body})
        print(f"Updated existing review note {existing['id']}")
    else:
        gitlab_request("POST", notes_url, token, {"body": full_body})
        print("Posted new review note")


def main():
    anthropic_key = env("ANTHROPIC_API_KEY")
    gitlab_token = env("GITLAB_API_TOKEN")
    server_url = env("CI_SERVER_URL")
    project_id = env("CI_PROJECT_ID")
    mr_iid = env("CI_MERGE_REQUEST_IID")
    mr_title = os.environ.get("CI_MERGE_REQUEST_TITLE", "")
    mr_description = os.environ.get("CI_MERGE_REQUEST_DESCRIPTION", "")

    changes_url = (
        f"{server_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes"
    )
    mr_data = gitlab_request("GET", changes_url, gitlab_token) or {}
    changes = mr_data.get("changes", [])

    if not changes:
        print("No changes found on this MR, skipping review.")
        return

    diff_text = build_diff_text(changes)
    if not diff_text.strip():
        print("No reviewable diff content (only lockfiles/binaries changed), skipping.")
        return

    review = call_claude(anthropic_key, diff_text, mr_title, mr_description)
    upsert_note(server_url, project_id, mr_iid, gitlab_token, review)


if __name__ == "__main__":
    main()
