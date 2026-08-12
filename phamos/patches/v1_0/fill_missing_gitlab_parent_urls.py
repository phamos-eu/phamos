import frappe


def execute():
    """
    Backfill custom_gitlab_parent_issue_url on Timesheets that already have a
    child URL but no parent URL.

    Logic mirrors the controller fix in TimesheetRecord.create_timesheet:
      - Use the linked Timesheet Record's parent issue URL when available.
      - Otherwise derive the parent from the child GitLab Issue.
      - If no parent can be resolved, fall back to the child URL itself.
    """
    if not frappe.db.has_column("Timesheet", "custom_gitlab_child_issue_url"):
        return
    if not frappe.db.has_column("Timesheet", "custom_gitlab_parent_issue_url"):
        return

    rows = frappe.db.sql(
        """
        SELECT
            ts.name,
            ts.custom_gitlab_child_issue_url,
            tsr.gitlab_issue,
            tsr.gitlab_parent_issue
        FROM `tabTimesheet` ts
        LEFT JOIN `tabTimesheet Record` tsr ON tsr.timesheet = ts.name
        WHERE ts.docstatus != 2
          AND IFNULL(ts.custom_gitlab_child_issue_url, '') != ''
          AND IFNULL(ts.custom_gitlab_parent_issue_url, '') = ''
        """,
        as_dict=True,
    )

    for r in rows:
        parent_url = None

        # 1. Prefer the parent issue already stored on the Timesheet Record.
        if r.gitlab_parent_issue:
            parent_url = frappe.db.get_value(
                "GitLab Issue", r.gitlab_parent_issue, "issue_url"
            )

        # 2. Derive parent from the child issue.
        if not parent_url and r.gitlab_issue:
            parent_issue = frappe.db.get_value(
                "GitLab Issue", r.gitlab_issue, "parent_issue"
            )
            if parent_issue:
                parent_url = frappe.db.get_value(
                    "GitLab Issue", parent_issue, "issue_url"
                )

        # 3. Final fallback: copy the child URL.
        if not parent_url:
            parent_url = r.custom_gitlab_child_issue_url

        frappe.db.set_value(
            "Timesheet",
            r.name,
            "custom_gitlab_parent_issue_url",
            parent_url,
            update_modified=False,
        )

    frappe.db.commit()
