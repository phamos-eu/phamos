import frappe
from frappe import _
from frappe.utils import now_datetime, add_to_date, time_diff_in_seconds, get_datetime


# ---------------------------------------------------------------------------
# Issue list
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_my_issues():
    """
    Return ALL open GitLab Issues with an `is_mine` flag.

    Matching priority:
    1. assignee_email (stored at sync time) compared against the user's ERPNext email.
    2. gitlab_username compared against the local part of the user's email
       (e.g. "simon.wanyama" matches "simon.wanyama@phamos.eu").
    3. No match → is_mine = False.
    """
    user = frappe.session.user

    user_email = (frappe.db.get_value("User", user, "email") or "").lower()
    user_email_local = user_email.split("@")[0]  # e.g. "simon.wanyama"

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

    # If there is a running session whose issue is closed/not in the opened list,
    # fetch it without a state filter and prepend it so the user can still stop it.
    if active_issue and active_issue not in {i["name"] for i in issues}:
        extra = frappe.get_all(
            "GitLab Issue",
            filters={"name": active_issue},
            fields=[
                "name", "issue_id", "title", "state",
                "due_date", "start_date",
                "assignee", "assignee_email", "gitlab_username",
                "issue_url", "parent_issue", "gitlab_project",
                "labels",
            ],
        )
        if extra:
            issues = extra + issues

    for issue in issues:
        ts_data = count_map.get(issue["name"], {"cnt": 0, "total_seconds": 0})
        issue["timesheet_count"] = ts_data["cnt"]
        issue["total_tracked_seconds"] = ts_data["total_seconds"]

        # 1. Email match; 2. gitlab_username matches local part of user email; 3. not mine
        assignee_email = (issue.get("assignee_email") or "").lower()
        gitlab_username = (issue.get("gitlab_username") or "").lower()
        if assignee_email:
            issue["is_mine"] = assignee_email == user_email
        elif gitlab_username:
            issue["is_mine"] = gitlab_username == user_email_local
        else:
            issue["is_mine"] = False

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
    last_idx = len(rows) - 1
    if last_row.get("to_time"):
        session_state = "paused"
    else:
        # Even index (0, 2, 4…) = work row → running
        # Odd index  (1, 3, 5…) = break row → paused
        session_state = "running" if last_idx % 2 == 0 else "paused"

    record["session_state"] = session_state
    record["elapsed_seconds"] = _calc_elapsed_seconds(rows)
    # Expose break_from so the frontend can show a live break timer without calling resume first
    if session_state == "paused" and not last_row.get("to_time"):
        record["break_from"] = str(last_row["from_time"])
    else:
        record["break_from"] = None
    return record


def _calc_elapsed_seconds(rows):
    total = 0
    for idx, row in enumerate(rows):
        if idx % 2 != 0:  # skip break rows (odd indices)
            continue
        if row.get("from_time") and row.get("to_time"):
            total += time_diff_in_seconds(row["to_time"], row["from_time"])
        elif row.get("from_time") and not row.get("to_time"):
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
def start_issue_timer(gitlab_issue_name, expected_time, goal=None, manual_start_time=None):
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
    
    # --- block duplicate drafts for this employee ---------------------------
    existing_drafts = frappe.get_all(
        "Timesheet Record",
        filters={"employee": employee.name, "docstatus": 0},
        fields=["name"],
        order_by="creation desc",
    )

    if existing_drafts:
        draft_links = ", ".join(
            f'<a href="/app/timesheet-record/{d["name"]}" target="_blank">{d["name"]}</a>'
            for d in existing_drafts[:3]
        )

        if len(existing_drafts) > 3:
            draft_links += ", ..."

        frappe.throw(
            _(
                "You already have draft Timesheet Record(s): {0}. "
                "Please submit or cancel them before starting a new timer."
            ).format(draft_links)
        )

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
    start_time = get_datetime(manual_start_time) if manual_start_time else now_datetime()
    ts = frappe.new_doc("Timesheet Record")
    ts.project = frappe_project
    ts.customer = customer
    ts.employee = employee.name
    ts.activity_type = employee.activity_type
    ts.goal = goal or issue.title  # default to issue title — the issue IS the goal
    ts.expected_time = expected_time
    ts.from_time = start_time
    ts.gitlab_issue = gitlab_issue_name
    ts.issues = issue.issue_url
    ts.parent_issues_url = issue.issue_url

    # First time-log row (open — no to_time, session is running)
    ts.append("item", {"from_time": start_time})

    ts.insert(ignore_permissions=True)
    frappe.db.commit()

    elapsed = int(time_diff_in_seconds(now_datetime(), start_time)) if manual_start_time else 0

    return {
        "name": ts.name,
        "from_time": str(start_time),
        "session_state": "running",
        "elapsed_seconds": elapsed,
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
    doc = frappe.get_doc("Timesheet Record", name)
    now = now_datetime()
    for row in reversed(doc.item):
        if not row.get("to_time"):
            row.to_time = now
            break
    doc.append("item", {"from_time": now})  # open break row starts immediately
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"session_state": "paused", "break_from": str(now)}


@frappe.whitelist()
def resume_timer(name):
    doc = frappe.get_doc("Timesheet Record", name)
    now = now_datetime()
    for row in reversed(doc.item):
        if not row.get("to_time"):
            row.to_time = now
            break
    doc.append("item", {"from_time": now})  # open new work row
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"session_state": "running"}


@frappe.whitelist()
def stop_timer(name, result, percent_billable=100, productivity=None, activity_type=None, manual_end_time=None):
    doc = frappe.get_doc("Timesheet Record", name)
    end_time = get_datetime(manual_end_time) if manual_end_time else now_datetime()

    # Close any open row (work or break)
    for row in reversed(doc.item):
        if not row.get("to_time"):
            row.to_time = end_time
            break

    # Calculate duration for every row
    for row in doc.item:
        if row.from_time and row.to_time:
            row.duration = time_diff_in_seconds(row.to_time, row.from_time)

    # Main timesheet uses only the first work row (index 0)
    if doc.item:
        first_row = doc.item[0]
        doc.from_time = first_row.from_time
        doc.to_time = first_row.to_time
        doc.actual_time = first_row.duration or 0

    doc.result = result
    doc.percent_billable = int(percent_billable)
    if activity_type:
        doc.activity_type = activity_type
    if productivity is not None:
        doc.productivity = productivity

    doc.save(ignore_permissions=True)
    doc.submit()
    frappe.db.commit()

    # Create separate submitted Timesheet Records for additional work segments (indices 2, 4, 6…)
    extra_names = []
    for i in range(2, len(doc.item), 2):
        alt_row = doc.item[i]
        if not (alt_row.from_time and alt_row.to_time):
            continue
        duration = time_diff_in_seconds(alt_row.to_time, alt_row.from_time)
        if duration <= 0:
            continue

        extra = frappe.new_doc("Timesheet Record")
        for field in ["project", "customer", "employee", "activity_type", "goal",
                      "issues", "expected_time", "result", "percent_billable",
                      "parent_issues_url", "gitlab_issue"]:
            extra.set(field, doc.get(field))
        if productivity is not None:
            extra.productivity = productivity
        extra.from_time = alt_row.from_time
        extra.to_time = alt_row.to_time
        extra.actual_time = duration
        extra.append("item", {
            "from_time": alt_row.from_time,
            "to_time": alt_row.to_time,
            "duration": duration,
        })
        extra.insert(ignore_permissions=True)
        extra.submit()
        extra_names.append(extra.name)

    frappe.db.commit()
    return {"name": doc.name, "session_state": "submitted", "extra_timesheets": extra_names}


@frappe.whitelist()
def get_gitlab_labels():
    """Return all GitLab Labels with their background and text colours."""
    return frappe.get_all(
        "GitLab Labels",
        fields=["name", "color", "text_color"],
        order_by="name asc",
    )


@frappe.whitelist()
def create_break_timesheet(from_time, to_time=None, project=None, goal=None, result=None, percent_billable=100, activity_type=None):
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, ["name", "activity_type"], as_dict=True)
    if not employee:
        frappe.throw(_("No Employee record linked to your user account."))

    from_dt = get_datetime(from_time)
    to_dt = get_datetime(to_time) if to_time else now_datetime()
    duration = time_diff_in_seconds(to_dt, from_dt)
    customer = frappe.db.get_value("Project", project, "customer")

    ts = frappe.new_doc("Timesheet Record")
    ts.project = project
    ts.customer = customer
    ts.employee = employee.name
    ts.activity_type = activity_type or employee.activity_type
    ts.goal = goal
    ts.result = result
    ts.from_time = from_dt
    ts.to_time = to_dt
    ts.actual_time = duration
    ts.expected_time = duration
    ts.percent_billable = int(percent_billable)
    ts.append("item", {"from_time": from_dt, "to_time": to_dt, "duration": duration})
    ts.insert(ignore_permissions=True)
    ts.submit()
    frappe.db.commit()

    return {"name": ts.name}
