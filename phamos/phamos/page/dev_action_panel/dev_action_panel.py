import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, time_diff_in_seconds


# ---------------------------------------------------------------------------
# Issue list
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_my_issues():
    """
    Return ALL open GitLab Issues with an `is_mine` flag.

    `is_mine` is True when the GitLab issue's `assignee` field matches
    the current user's Employee employee_name (primary) or User full_name
    (fallback). Email-based matching is intentionally excluded — the GitLab
    token often lacks read_user scope so get_user_email() returns the token
    owner's email for every user, making email matching unreliable.
    """
    user = frappe.session.user

    # Build set of display names that identify "me"
    mine_names = set()
    employee_name = frappe.db.get_value("Employee", {"user_id": user}, "employee_name")
    if employee_name:
        mine_names.add(employee_name)
    full_name = frappe.db.get_value("User", user, "full_name")
    if full_name:
        mine_names.add(full_name)

    # --- fetch ALL open issues -----------------------------------------------
    issues = frappe.get_all(
        "GitLab Issue",
        filters={"state": "opened"},
        fields=[
            "name", "issue_id", "title", "state",
            "due_date", "start_date",
            "assignee", "assignee_email", "gitlab_username",
            "issue_url", "parent_issue", "gitlab_project",
            "labels",
        ],
        order_by="due_date asc, modified desc",
    )

    # --- bulk-fetch timesheet counts + total tracked time per issue ----------
    if issues:
        issue_names = [i["name"] for i in issues]
        rows = frappe.db.sql(
            """
            SELECT gitlab_issue,
                   COUNT(*) AS cnt,
                   COALESCE(SUM(CASE WHEN docstatus = 1 THEN actual_time ELSE 0 END), 0) AS total_seconds
            FROM `tabTimesheet Record`
            WHERE gitlab_issue IN %(names)s AND docstatus != 2
            GROUP BY gitlab_issue
            """,
            {"names": issue_names},
            as_dict=True,
        )
        count_map = {r["gitlab_issue"]: {"cnt": r["cnt"], "total_seconds": int(r["total_seconds"])} for r in rows}
    else:
        count_map = {}

    # --- enrich each issue ---------------------------------------------------
    active = _get_active_session_raw(user)
    active_ts_name = active.get("name") if active else None
    active_issue = active.get("gitlab_issue") if active else None

    for issue in issues:
        ts_data = count_map.get(issue["name"], {"cnt": 0, "total_seconds": 0})
        issue["timesheet_count"] = ts_data["cnt"]
        issue["total_tracked_seconds"] = ts_data["total_seconds"]

        # Primary: assignee == employee_name; fallback: assignee == user full_name
        issue["is_mine"] = bool(issue.get("assignee") and issue["assignee"] in mine_names)

        # Resolve parent title for display
        if issue.get("parent_issue"):
            issue["parent_issue_id"] = frappe.db.get_value(
                "GitLab Issue", issue["parent_issue"], "issue_id"
            )
            issue["parent_issue_title"] = frappe.db.get_value(
                "GitLab Issue", issue["parent_issue"], "title"
            )
        else:
            issue["parent_issue_id"] = None
            issue["parent_issue_title"] = None

        # Resolve GitLab Project display name
        if issue.get("gitlab_project"):
            issue["gitlab_project_title"] = frappe.db.get_value(
                "GitLab Project", issue["gitlab_project"], "title"
            )
        else:
            issue["gitlab_project_title"] = None

        # Mark which issue (if any) has a running/paused session
        if active_issue == issue["name"]:
            issue["active_timesheet"] = active_ts_name
            issue["session_state"] = active.get("session_state")  # "running" | "paused"
        else:
            issue["active_timesheet"] = None
            issue["session_state"] = None

    return issues


# ---------------------------------------------------------------------------
# Active session helpers
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_active_session():
    """
    Return the currently running or paused Timesheet Record for this user,
    or None if no session is open.
    """
    user = frappe.session.user
    return _get_active_session_raw(user)


def _get_active_session_raw(user):
    """
    Internal (no whitelist) version — shared by get_my_issues() and get_active_session().
    Returns a dict with session details, or None.
    """
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return None

    # Only track sessions created by the cockpit (must have gitlab_issue set).
    # This avoids picking up old legacy draft records that were never submitted.
    open_records = frappe.get_all(
        "Timesheet Record",
        filters={
            "employee": employee,
            "docstatus": 0,
            "gitlab_issue": ["!=", ""],
        },
        fields=["name", "goal", "from_time", "gitlab_issue", "project"],
        order_by="creation desc",
        limit=1,
    )

    if not open_records:
        return None

    record = open_records[0]

    # Determine whether it is running or paused by counting child rows
    rows = frappe.get_all(
        "Timesheet Record Item",
        filters={"parent": record["name"]},
        fields=["name", "from_time", "to_time"],
        order_by="idx asc",
    )

    if not rows:
        return None

    last_row = rows[-1]
    if last_row.get("to_time"):
        # All rows are closed — session is paused (even row count)
        session_state = "paused"
    else:
        # Last row is open — session is running (odd row count)
        session_state = "running"

    record["session_state"] = session_state
    record["elapsed_seconds"] = _calc_elapsed_seconds(rows)
    return record


def _calc_elapsed_seconds(rows):
    """Sum all closed intervals plus the current open interval if running."""
    total = 0
    for row in rows:
        if row.get("from_time") and row.get("to_time"):
            total += time_diff_in_seconds(row["to_time"], row["from_time"])
        elif row.get("from_time") and not row.get("to_time"):
            # Open interval — count up to now
            total += time_diff_in_seconds(now_datetime(), row["from_time"])
    return int(total)


# ---------------------------------------------------------------------------
# Start timer
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_issue_timesheets(gitlab_issue_name):
    """Return all Timesheet Records (non-cancelled) for a given GitLab issue, newest first."""
    records = frappe.get_all(
        "Timesheet Record",
        filters={"gitlab_issue": gitlab_issue_name, "docstatus": ["!=", 2]},
        fields=["name", "from_time", "to_time", "actual_time", "goal", "result", "docstatus", "employee"],
        order_by="from_time desc",
    )
    return records


@frappe.whitelist()
def start_issue_timer(gitlab_issue_name, expected_time, goal=None):
    """
    Create a Timesheet Record from a GitLab Issue, auto-resolving:
      - project   ← GitLab Issue → GitLab Project → frappe_project
      - customer  ← ERPNext Project → customer
      - employee  ← session user → Employee
      - activity_type ← Employee default
      - issue_url ← GitLab Issue.issue_url

    Raises a user-visible error if the GitLab Project has no frappe_project mapped.
    """
    user = frappe.session.user

    # --- resolve employee ----------------------------------------------------
    employee = frappe.db.get_value(
        "Employee", {"user_id": user}, ["name", "activity_type"], as_dict=True
    )
    if not employee:
        frappe.throw(_("No Employee record linked to your user account."))

    # --- resolve issue -------------------------------------------------------
    issue = frappe.get_doc("GitLab Issue", gitlab_issue_name)

    if not issue.gitlab_project:
        frappe.throw(_(f"GitLab Issue {issue.issue_id} has no GitLab Project linked."))

    # --- resolve ERPNext project via GitLab Project --------------------------
    frappe_project = frappe.db.get_value(
        "GitLab Project", issue.gitlab_project, "frappe_project"
    )
    if not frappe_project:
        frappe.throw(
            _(
                f"GitLab Project '{issue.gitlab_project}' has no ERPNext Project mapped. "
                "Please set the 'ERPNext Project' field on the GitLab Project record."
            )
        )

    # --- resolve customer from ERPNext project -------------------------------
    customer = frappe.db.get_value("Project", frappe_project, "customer")

    # --- create the Timesheet Record -----------------------------------------
    now = now_datetime()
    ts = frappe.new_doc("Timesheet Record")
    ts.project = frappe_project
    ts.customer = customer
    ts.employee = employee.name
    ts.activity_type = employee.activity_type
    ts.goal = goal or issue.title  # default to issue title — the issue IS the goal
    ts.expected_time = expected_time
    ts.from_time = now
    ts.gitlab_issue = gitlab_issue_name
    ts.issues = issue.issue_url
    ts.parent_issues_url = issue.issue_url

    # First time-log row (open — no to_time yet)
    ts.append("item", {"from_time": now})

    ts.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": ts.name,
        "from_time": str(now),
        "session_state": "running",
        "elapsed_seconds": 0,
    }


# ---------------------------------------------------------------------------
# Stats bar
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_time_stats():
    """
    Return working and billable totals for today, this week, and this month.
    Reads from submitted Timesheet Records for the current employee.
    """
    from frappe.utils import (
        get_first_day, get_last_day, nowdate, getdate, add_days
    )

    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return _empty_stats()

    today = getdate(nowdate())

    # Week: Mon–Sun
    week_start = add_days(today, -today.weekday())
    week_end = add_days(week_start, 6)

    # Month
    month_start = get_first_day(today)
    month_end = get_last_day(today)

    def fetch(date_from, date_to):
        rows = frappe.db.sql(
            """
            SELECT
                SUM(tr.actual_time)                              AS total_seconds,
                SUM(tr.actual_time * tr.percent_billable / 100) AS billable_seconds
            FROM `tabTimesheet Record` tr
            WHERE tr.employee = %(employee)s
              AND tr.docstatus != 2
              AND DATE(tr.creation) BETWEEN %(from)s AND %(to)s
            """,
            {"employee": employee, "from": date_from, "to": date_to},
            as_dict=True,
        )
        row = rows[0] if rows else {}
        return {
            "total_seconds": int(row.get("total_seconds") or 0),
            "billable_seconds": int(row.get("billable_seconds") or 0),
        }

    return {
        "today": fetch(today, today),
        "week": fetch(week_start, week_end),
        "month": fetch(month_start, month_end),
    }


def _empty_stats():
    empty = {"total_seconds": 0, "billable_seconds": 0}
    return {"today": empty, "week": empty, "month": empty}


# ---------------------------------------------------------------------------
# Pause / Resume / Stop
# ---------------------------------------------------------------------------

@frappe.whitelist()
def pause_timer(name):
    """
    Close the currently open item row to pause the session.
    Does NOT add a new row — resume will add one.
    """
    doc = frappe.get_doc("Timesheet Record", name)
    now = now_datetime()
    for row in reversed(doc.item):
        if not row.get("to_time"):
            row.to_time = now
            break
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"session_state": "paused"}


@frappe.whitelist()
def resume_timer(name):
    """
    Add a new open item row to resume a paused session.
    """
    doc = frappe.get_doc("Timesheet Record", name)
    now = now_datetime()
    doc.append("item", {"from_time": now})
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"session_state": "running"}


@frappe.whitelist()
def stop_timer(name, result, percent_billable=100, productivity=None, activity_type=None):
    """
    Close the open row (if running), calculate actual_time from all item rows,
    fill in result fields, and submit the Timesheet Record.

    All item rows are work intervals (no break rows in this flow).
    actual_time = sum of all row durations.
    """
    doc = frappe.get_doc("Timesheet Record", name)
    now = now_datetime()

    # Close the open row if the session is currently running
    for row in reversed(doc.item):
        if not row.get("to_time"):
            row.to_time = now
            break

    # Calculate duration for each row and sum
    total_seconds = 0
    for row in doc.item:
        if row.from_time and row.to_time:
            row.duration = time_diff_in_seconds(row.to_time, row.from_time)
            total_seconds += row.duration

    # Set parent-level time fields required by before_submit and create_timesheet
    if doc.item:
        doc.from_time = doc.item[0].from_time
        doc.to_time = now

    doc.actual_time = total_seconds
    doc.result = result
    doc.percent_billable = int(percent_billable)
    if activity_type:
        doc.activity_type = activity_type
    if productivity is not None:
        doc.productivity = productivity

    doc.save(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()

    return {"name": doc.name, "session_state": "submitted"}
