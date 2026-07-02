# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import json
from datetime import datetime, timedelta

import frappe
import requests
from frappe.auth import get_decrypted_password
from frappe.utils import get_first_day_of_week, now_datetime, nowdate

from .gitlab_utils import get_gitlab_headers

PROD_LABELS = ["Merged into Production", "Testing on Production"]
PROD_LABEL_FIELDS = {
    "Merged into Production": "merged_to_production_at",
    "Testing on Production": "testing_on_production_at",
}

# Activity types as defined in patches/v1_0/add_activity_types_update.py
CUSTOMER_ACTIVITY_TYPES = ["Working with Customer"]
INTERNAL_ACTIVITY_TYPES = ["Working alone", "Working with Team"]


def _get_week_range(from_date=None, to_date=None):
    if from_date and to_date:
        return str(from_date), str(to_date)
    today = nowdate()
    # Monday of current week
    week_start = get_first_day_of_week(today)
    week_end = str((datetime.strptime(str(week_start), "%Y-%m-%d") + timedelta(days=6)).date())
    return str(week_start), week_end


def sync_production_label_timestamps(implementation_name):
    """
    For all GitLab projects linked to this implementation, fetch label events
    from the GitLab API to populate merged_to_production_at / testing_on_production_at
    on any GitLab Issue that currently has those labels but lacks the timestamp.
    """
    settings = frappe.get_single("GitLab Settings")
    headers = get_gitlab_headers()
    base_url = settings.gitlab_url.rstrip("/")

    projects = frappe.get_all(
        "GitLab Project",
        filters={"implementation": implementation_name},
        fields=["name", "project_id"],
    )

    for project in projects:
        for label_name, field_name in PROD_LABEL_FIELDS.items():
            page = 1
            while True:
                resp = requests.get(
                    f"{base_url}/api/v4/projects/{project.project_id}/issues",
                    headers=headers,
                    params={"labels": label_name, "state": "all", "per_page": 100, "page": page},
                    timeout=30,
                )
                if resp.status_code != 200:
                    break
                issues = resp.json()
                if not issues:
                    break

                for issue in issues:
                    issue_iid = str(issue["iid"])
                    doc_name = frappe.db.get_value(
                        "GitLab Issue",
                        {"issue_id": issue_iid, "gitlab_project": project.name},
                        "name",
                    )
                    if not doc_name:
                        continue

                    existing_ts = frappe.db.get_value("GitLab Issue", doc_name, field_name)
                    if existing_ts:
                        continue

                    # Fetch label events to find the add timestamp
                    events_resp = requests.get(
                        f"{base_url}/api/v4/projects/{project.project_id}/issues/{issue_iid}/resource_label_events",
                        headers=headers,
                        timeout=30,
                    )
                    if events_resp.status_code != 200:
                        continue

                    added_at = None
                    for event in events_resp.json():
                        if (
                            event.get("action") == "add"
                            and event.get("label", {}).get("name") == label_name
                        ):
                            added_at = event.get("created_at")
                            break

                    if added_at:
                        # GitLab returns ISO 8601 with Z; convert to naive datetime for Frappe
                        try:
                            dt = datetime.strptime(added_at, "%Y-%m-%dT%H:%M:%S.%fZ")
                        except ValueError:
                            dt = datetime.strptime(added_at, "%Y-%m-%dT%H:%M:%SZ")
                        frappe.db.set_value("GitLab Issue", doc_name, field_name, dt)

                page += 1

    frappe.db.commit()


def get_deployed_issues(implementation_name, from_date, to_date):
    """
    Return GitLab Issues where merged_to_production_at or testing_on_production_at
    falls within [from_date, to_date] for projects linked to this implementation.
    """
    project_names = frappe.get_all(
        "GitLab Project",
        filters={"implementation": implementation_name},
        pluck="name",
    )
    if not project_names:
        return []

    from_dt = f"{from_date} 00:00:00"
    to_dt = f"{to_date} 23:59:59"

    issues = frappe.db.sql(
        """
        SELECT
            name, issue_id, title, description, state,
            labels, issue_url, assignee,
            merged_to_production_at, testing_on_production_at
        FROM `tabGitLab Issue`
        WHERE gitlab_project IN %(projects)s
          AND (
              (merged_to_production_at BETWEEN %(from_dt)s AND %(to_dt)s)
              OR (testing_on_production_at BETWEEN %(from_dt)s AND %(to_dt)s)
          )
        ORDER BY COALESCE(merged_to_production_at, testing_on_production_at)
        """,
        {"projects": project_names, "from_dt": from_dt, "to_dt": to_dt},
        as_dict=True,
    )
    if not issues:
        return issues

    comments = frappe.get_all(
        "GitLab Issue Comment",
        filters={"parent": ["in", [issue.name for issue in issues]]},
        fields=["parent", "author", "comment", "commented_at"],
        order_by="commented_at asc",
    )
    comments_by_issue = {}
    for c in comments:
        comments_by_issue.setdefault(c.parent, []).append(c)

    for issue in issues:
        issue["comments"] = comments_by_issue.get(issue.name, [])

    return issues


def get_timesheet_breakdown(implementation_name, from_date, to_date):
    """
    Return total hours for the week, split by:
      - customer_hours  (Working with Customer)
      - internal_hours  (Working alone + Working with Team)
    """
    project_names = frappe.get_all(
        "Project",
        filters={"custom_implementation": implementation_name},
        pluck="name",
    )
    if not project_names:
        return {"total": 0.0, "customer": 0.0, "internal_alone": 0.0, "internal_team": 0.0}

    rows = frappe.db.sql(
        """
        SELECT tsd.activity_type, SUM(tsd.hours) AS hours
        FROM `tabTimesheet Detail` tsd
        JOIN `tabTimesheet` ts ON ts.name = tsd.parent
        WHERE ts.docstatus IN (0, 1)
          AND tsd.project IN %(projects)s
          AND DATE(tsd.from_time) BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY tsd.activity_type
        """,
        {"projects": project_names, "from_date": from_date, "to_date": to_date},
        as_dict=True,
    )

    result = {"total": 0.0, "customer": 0.0, "internal_alone": 0.0, "internal_team": 0.0}
    for row in rows:
        h = float(row.hours or 0)
        result["total"] += h
        atype = row.activity_type or ""
        if atype == "Working with Customer":
            result["customer"] += h
        elif atype == "Working alone":
            result["internal_alone"] += h
        elif atype == "Working with Team":
            result["internal_team"] += h

    return result


def _format_issues_for_prompt(issues):
    if not issues:
        return "No tickets found for this period."
    lines = []
    for issue in issues:
        label_note = ""
        if issue.get("merged_to_production_at"):
            label_note = "(Merged to Production)"
        elif issue.get("testing_on_production_at"):
            label_note = "(Testing on Production)"
        desc = (issue.get("description") or "").strip()
        # Truncate long descriptions
        if len(desc) > 400:
            desc = desc[:397] + "..."

        comments_text = "(no comments)"
        comment_rows = issue.get("comments") or []
        if comment_rows:
            comment_lines = []
            for c in comment_rows:
                body = (c.get("comment") or "").strip()
                if len(body) > 300:
                    body = body[:297] + "..."
                comment_lines.append(f"    - {c.get('author', 'unknown')}: {body}")
            comments_text = "\n".join(comment_lines)

        lines.append(
            f"- #{issue['issue_id']}: {issue['title']} {label_note}\n"
            f"  URL: {issue.get('issue_url', '')}\n"
            f"  Description: {desc or '(no description)'}\n"
            f"  Comments:\n{comments_text}"
        )
    return "\n".join(lines)


def _call_mistral(system_prompt, user_message):
    try:
        settings = frappe.get_single("phamos Settings")
        api_key = settings.get_password("mistral_api_key") if settings.get("mistral_api_key") else None
        if not api_key:
            frappe.throw("Mistral API key not configured in phamos Settings.")
        model = getattr(settings, "weekly_report_mistral_model", None) or "mistral-small-latest"
        base_url = (getattr(settings, "mistral_base_url", None) or "").strip() or "https://api.mistral.ai/v1"
    except Exception:
        frappe.throw("Could not load Mistral settings from phamos Settings.")

    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.4,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _get_report_prompt(implementation_name):
    specific = frappe.db.get_value(
        "Customer Weekly Report Settings",
        {"implementation": implementation_name, "enabled": 1},
        "prompt",
    )
    if specific:
        return specific

    default = frappe.db.get_value(
        "Customer Weekly Report Settings",
        {"is_default": 1, "enabled": 1},
        "prompt",
    )
    return default or None


def _get_stakeholder_emails(implementation_name):
    rows = frappe.db.get_all(
        "Implementation Stakeholder",
        filters={"parent": implementation_name, "receive_weekly_customer_report": 1},
        fields=["email"],
    )
    return [r.email for r in rows if r.email]


@frappe.whitelist()
def generate_and_send_weekly_report(implementation_name, from_date=None, to_date=None):
    """
    Orchestrates the weekly customer report:
      1. Syncs prod label timestamps from GitLab
      2. Fetches deployed issues for the week
      3. Fetches timesheet breakdown
      4. Calls Mistral to generate the report body
      5. Sends the email to stakeholders marked receive_weekly_customer_report
    """
    from_date, to_date = _get_week_range(from_date, to_date)

    prompt = _get_report_prompt(implementation_name)
    if not prompt:
        frappe.throw(
            "No Customer Weekly Report Settings found. "
            "Please create one (default or implementation-specific)."
        )

    recipients = _get_stakeholder_emails(implementation_name)
    if not recipients:
        frappe.throw(
            "No stakeholders with 'Weekly Report' enabled found for this implementation."
        )

    # Step 1: sync timestamps so query is fresh
    try:
        sync_production_label_timestamps(implementation_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "Weekly Report: label timestamp sync failed")

    # Step 2: collect data
    issues = get_deployed_issues(implementation_name, from_date, to_date)
    timesheet = get_timesheet_breakdown(implementation_name, from_date, to_date)

    implementation = frappe.get_doc("Implementation", implementation_name)
    customer_name = frappe.db.get_value("Customer", implementation.customer, "customer_name") if implementation.customer else implementation_name

    issues_text = _format_issues_for_prompt(issues)
    timesheet_text = (
        f"Total hours this week: {timesheet['total']:.1f}h\n"
        f"  - Customer Meetings (Working with Customer): {timesheet['customer']:.1f}h\n"
        f"  - Internal / Team work (Working with Team): {timesheet['internal_team']:.1f}h\n"
        f"  - Internal / Solo work (Working alone): {timesheet['internal_alone']:.1f}h"
    )

    system_prompt = (
        "You are a professional report writer for a software consultancy called phamos. "
        "Write concise, professional weekly progress reports for customers. "
        "Use clear, non-technical language. Format the report with a brief intro, "
        "a section per deployed ticket (1-2 sentences each), and a time summary at the end. "
        "Write in the language that best matches the customer context (default: German unless English is clearly appropriate)."
    )

    user_message = (
        f"Customer: {customer_name}\n"
        f"Report period: {from_date} to {to_date}\n\n"
        f"Instructions: {prompt}\n\n"
        f"Deployed tickets:\n{issues_text}\n\n"
        f"Time tracking:\n{timesheet_text}"
    )

    # Step 3: generate report
    report_body = _call_mistral(system_prompt, user_message)

    # Step 4: send email
    subject = f"Wochenbericht {from_date} – {to_date} | {customer_name}"

    email_body = (
        f"<b><i>phamos wünscht einen wunderschönen guten Morgen!</i></b><br><br>"
        f"{report_body.replace(chr(10), '<br>')}"
        f"<br><br>Bei Fragen wenden Sie sich bitte an Ihren Projektleiter. Vielen Dank.<br><br>"
        f"Wir wünschen eine gute Woche!<br><b>Ihr team phamos</b>"
    )

    frappe.sendmail(
        recipients=recipients,
        subject=subject,
        message=email_body,
        now=True,
    )

    return {
        "status": "sent",
        "recipients": recipients,
        "issues_count": len(issues),
        "from_date": from_date,
        "to_date": to_date,
    }


@frappe.whitelist()
def send_weekly_reports_for_all_implementations(from_date=None, to_date=None):
    """
    Scheduled entrypoint (see hooks.py "cron" — Monday mornings) and manual test button
    (GitLab Settings). Generates & sends the weekly customer report for every Implementation
    that has at least one stakeholder opted in via 'Weekly Report'. Each implementation is
    isolated so one failure (missing prompt settings, GitLab API error, etc.) doesn't block the rest.
    """
    implementation_names = frappe.db.sql_list(
        """
        SELECT DISTINCT parent
        FROM `tabImplementation Stakeholder`
        WHERE receive_weekly_customer_report = 1
        """
    )

    results = {"sent": [], "failed": []}
    for implementation_name in implementation_names:
        try:
            generate_and_send_weekly_report(implementation_name, from_date, to_date)
            results["sent"].append(implementation_name)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), f"Weekly Report Failed - {implementation_name}"
            )
            results["failed"].append(implementation_name)

    return results
