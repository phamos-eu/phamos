import frappe
from frappe import _
from frappe.utils import cint, cstr, now_datetime, add_to_date, time_diff_in_seconds, get_datetime
from phamos.phamos.timesheet_utils import (
    billable_seconds_sql,
    billable_seconds_term,
    billing_context,
    percent_billable_or_preset,
    percent_billable_preset,
)
from phamos.phamos.doctype.timesheet_record.timesheet_record import compute_time_limit_status
from phamos.gitlab_integration.issue_refs import issue_created_during, link_gitlab_issues
from frappe.query_builder import Order
from frappe.query_builder.functions import Coalesce, Sum, Count, Max
from pypika import Case


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

    if not issues:
        return issues

    issue_names = [i["name"] for i in issues]
    timesheets = _timesheet_totals_by_issue(issue_names)
    child_count = _child_count_by_issue(issue_names)
    projects = _gitlab_projects({i["gitlab_project"] for i in issues if i.get("gitlab_project")})
    parents = {
        p.name: p
        for p in frappe.get_all(
            "GitLab Issue",
            filters={"name": ["in", list({i["parent_issue"] for i in issues if i.get("parent_issue")})]},
            fields=["name", "issue_id", "title"],
        )
    }

    for issue in issues:
        ts_data = timesheets.get(issue["name"], {"cnt": 0, "total_seconds": 0})
        issue["timesheet_count"] = ts_data["cnt"]
        issue["total_tracked_seconds"] = ts_data["total_seconds"]
        issue["child_count"] = child_count.get(issue["name"], 0)

        gitlab_project = projects.get(issue.get("gitlab_project")) or {}
        issue["gitlab_project_title"] = gitlab_project.get("title")
        issue["project"] = gitlab_project.get("frappe_project")
        issue["project_name"] = gitlab_project.get("project_name") or issue["project"]

        parent = parents.get(issue.get("parent_issue")) or {}
        issue["parent_issue_id"] = parent.get("issue_id")
        issue["parent_issue_title"] = parent.get("title")

        # 1. Email match; 2. gitlab_username matches local part of user email; 3. not mine
        assignee_email = (issue.get("assignee_email") or "").lower()
        gitlab_username = (issue.get("gitlab_username") or "").lower()
        if assignee_email:
            issue["is_mine"] = assignee_email == user_email
        elif gitlab_username:
            issue["is_mine"] = gitlab_username == user_email_local
        else:
            issue["is_mine"] = False

        # Mark which issue (if any) has a running/paused session
        if active_issue == issue["name"]:
            issue["active_timesheet"] = active_ts_name
            issue["session_state"] = active.get("session_state")  # "running" | "paused"
        else:
            issue["active_timesheet"] = None
            issue["session_state"] = None

    return issues


def _timesheet_totals_by_issue(issue_names):
    """{issue: {"cnt", "total_seconds"}}: non-cancelled records, submitted time only."""
    record = frappe.qb.DocType("Timesheet Record")
    submitted_seconds = Sum(Case().when(record.docstatus == 1, record.actual_time).else_(0))
    rows = (
        frappe.qb.from_(record)
        .select(record.gitlab_issue, Count("*").as_("cnt"), Coalesce(submitted_seconds, 0).as_("total_seconds"))
        .where(record.gitlab_issue.isin(issue_names) & (record.docstatus != 2))
        .groupby(record.gitlab_issue)
    ).run(as_dict=True)
    return {r.gitlab_issue: {"cnt": r.cnt, "total_seconds": int(r.total_seconds)} for r in rows}


def _child_count_by_issue(issue_names):
    """{issue: number of child issues in any state}."""
    issue = frappe.qb.DocType("GitLab Issue")
    rows = (
        frappe.qb.from_(issue)
        .select(issue.parent_issue, Count("*").as_("cnt"))
        .where(issue.parent_issue.isin(issue_names))
        .groupby(issue.parent_issue)
    ).run(as_dict=True)
    return {r.parent_issue: r.cnt for r in rows}


def _gitlab_projects(names):
    """{GitLab Project: {"title", "frappe_project", "project_name"}}."""
    if not names:
        return {}
    gitlab_project = frappe.qb.DocType("GitLab Project")
    project = frappe.qb.DocType("Project")
    rows = (
        frappe.qb.from_(gitlab_project)
        .left_join(project)
        .on(project.name == gitlab_project.frappe_project)
        .select(gitlab_project.name, gitlab_project.title, gitlab_project.frappe_project, project.project_name)
        .where(gitlab_project.name.isin(list(names)))
    ).run(as_dict=True)
    return {r.name: r for r in rows}


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
    record["project_percent_billable"] = billing_context(record["project"])["percent_billable"]
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
    ts.gitlab_parent_issue = issue.parent_issue if issue.parent_issue else gitlab_issue_name
    ts.percent_billable = billing_context(frappe_project)["percent_billable"]

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
            f"""
            SELECT
                SUM(tr.actual_time)                     AS total_seconds,
                SUM({billable_seconds_sql("tr")})       AS billable_seconds
            FROM `tabTimesheet Record` tr
            WHERE tr.employee = %(employee)s
              AND tr.docstatus != 2
              AND DATE(tr.from_time) BETWEEN %(from)s AND %(to)s
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
def stop_timer(name, result, percent_billable=None, activity_type=None, manual_end_time=None, value_add=100, gitlab_issue_ref=None):
    """Stop and submit. `gitlab_issue_ref`: GitLab ticket picked or pasted on Stop; without it,
    URLs in Goal / Result are used. Either way child and parent issue are worked out."""
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
    link_gitlab_issues(doc, reference=gitlab_issue_ref, texts=(doc.goal, result))
    if not doc.gitlab_issue and not doc.gitlab_parent_issue:
        # Project timer without a ticket: the newest ticket created in this project while it ran,
        # mine or unassigned.
        user = frappe.db.get_value("Employee", doc.employee, "user_id") or frappe.session.user
        link_gitlab_issues(doc, reference=issue_created_during(doc.project, doc.from_time, end_time, user))
    doc.percent_billable = percent_billable_or_preset(percent_billable, doc.project)
    doc.value_add = cstr(value_add)
    if activity_type:
        doc.activity_type = activity_type

    time_limit_status = compute_time_limit_status(doc)
    if time_limit_status.get("exceeds"):
        doc.save(ignore_permissions=True)
        frappe.db.commit()
        time_limit_status["name"] = doc.name
        time_limit_status["session_state"] = "exceeds_time_limit"
        return time_limit_status

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
                      "gitlab_issue", "gitlab_parent_issue", "expected_time", "result",
                      "percent_billable", "value_add"]:
            extra.set(field, doc.get(field))
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
def create_break_timesheet(from_time, to_time=None, project=None, goal=None, result=None, percent_billable=None, activity_type=None, value_add=100, gitlab_issue_ref=None):
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
    link_gitlab_issues(ts, reference=gitlab_issue_ref, texts=(goal, result))
    ts.from_time = from_dt
    ts.to_time = to_dt
    ts.actual_time = duration
    ts.expected_time = duration
    ts.percent_billable = percent_billable_or_preset(percent_billable, project)
    ts.value_add = cstr(value_add)
    ts.append("item", {"from_time": from_dt, "to_time": to_dt, "duration": duration})
    ts.insert(ignore_permissions=True)
    ts.submit()
    frappe.db.commit()

    return {"name": ts.name}


# ---------------------------------------------------------------------------
# Projects section
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_dev_my_projects():
    """Return projects assigned to the current user via open ToDo records."""
    user = frappe.session.user

    Project = frappe.qb.DocType("Project")
    Customer = frappe.qb.DocType("Customer")
    ToDo = frappe.qb.DocType("ToDo")

    query = (
        frappe.qb.from_(Project)
        .left_join(Customer)
        .on(Customer.name == Project.customer)
        .join(ToDo)
        .on(
            (ToDo.reference_name == Project.name)
            & (ToDo.reference_type == "Project")
            & (ToDo.status == "Open")
            & (ToDo.allocated_to == user)
        )
        .select(
            Project.name,
            Project.project_name,
            Project.status,
            Project.percent_billable,
            Project.customer,
            Coalesce(Customer.customer_name, Project.customer).as_("customer_desc"),
        )
        .distinct()
        .orderby(Project.project_name, order=Order.asc)
    )
    projects = query.run(as_dict=True)
    return _enrich_projects(projects, user)

@frappe.whitelist()
def get_dev_all_projects():
    """One project list instead of "My Projects" + "All Projects".

    Every Open project, plus projects assigned to me in any status. Assigned means an open or
    closed (done) assignment ToDo, so a project stays mine after the ToDo is ticked off; a
    cancelled assignment does not count. Order: assigned to me first, then the rest; within
    each, last used first (my latest Timesheet Record), then by name.
    """
    user = frappe.session.user

    Project = frappe.qb.DocType("Project")
    Customer = frappe.qb.DocType("Customer")

    assigned_to_me = _assigned_to_me(Project, user)
    is_assigned = Case().when(assigned_to_me.isnotnull(), 1).else_(0).as_("is_assigned")

    query = (
        frappe.qb.from_(Project)
        .left_join(Customer)
        .on(Customer.name == Project.customer)
        .select(
            Project.name,
            Project.project_name,
            Project.status,
            Project.percent_billable,
            Project.customer,
            Coalesce(Customer.customer_name, Project.customer).as_("customer_desc"),
            is_assigned,
        )
        .where((Project.status == "Open") | assigned_to_me.isnotnull())
    )
    projects = _enrich_projects(query.run(as_dict=True), user)
    projects.sort(
        key=lambda p: (
            -cint(p.get("is_assigned")),
            -(get_datetime(p["last_used"]).timestamp() if p.get("last_used") else 0),
            (p.get("project_name") or "").lower(),
        )
    )
    return projects


def _assigned_to_me(Project, user):
    """Subquery: the project has an open or closed (done) assignment ToDo for the user.
    A subquery, not a join: several ToDos for one project would duplicate the row."""
    ToDo = frappe.qb.DocType("ToDo")
    return (
        frappe.qb.from_(ToDo)
        .select(Max(ToDo.reference_name))
        .where(
            (ToDo.reference_name == Project.name)
            & (ToDo.reference_type == "Project")
            & (ToDo.status.isin(["Open", "Closed"]))
            & (ToDo.allocated_to == user)
        )
    )


def _dev_project_names(user):
    """Names get_dev_all_projects lists: every Open project plus those assigned to the user."""
    Project = frappe.qb.DocType("Project")
    return set(
        frappe.qb.from_(Project)
        .select(Project.name)
        .where((Project.status == "Open") | _assigned_to_me(Project, user).isnotnull())
        .run(pluck=True)
    )


# The fields the panel itself already shows for each record (get_my_issues /
# get_dev_all_projects). Filtering is limited to them, so the Filter button cannot be used to
# probe values of fields the user never sees (a filter on a hidden field tells, record by
# record, whether its value matches).
FILTERABLE_FIELDS = {
    "GitLab Issue": frozenset(
        {
            "name", "issue_id", "title", "state", "due_date", "start_date",
            "assignee", "assignee_email", "gitlab_username",
            "issue_url", "parent_issue", "gitlab_project", "labels",
        }
    ),
    "Project": frozenset({"name", "project_name", "status", "percent_billable", "customer"}),
}
FILTERABLE_DOCTYPES = tuple(FILTERABLE_FIELDS)


@frappe.whitelist()
def get_matching_names(doctype, filters):
    """Names of the records that match a Frappe filter group, for the panel's Filter button.

    The panel loads its full lists once and only hides rows, so sidebar counts and the running
    timer stay as they are. It uses get_all (GitLab Issue is readable by System Manager only, like
    get_my_issues), so it answers only what the panel already shows: panel users (a linked
    Employee), the panel's records (open GitLab Issues; Open or assigned projects) and the
    panel's fields (FILTERABLE_FIELDS), never a child table or another doctype.
    """
    if doctype not in FILTERABLE_DOCTYPES:
        frappe.throw(_("Filtering {0} is not supported here.").format(doctype))
    user = frappe.session.user
    if not frappe.db.exists("Employee", {"user_id": user}):
        frappe.throw(_("No Employee record linked to your user account."), frappe.PermissionError)
    filters = _filter_rows(doctype, filters)
    if doctype == "GitLab Issue":
        return frappe.get_all(doctype, filters=[*filters, [doctype, "state", "=", "opened"]], pluck="name")
    allowed = _dev_project_names(user)
    return [name for name in frappe.get_all(doctype, filters=filters, pluck="name") if name in allowed]


def _filter_rows(doctype, filters):
    """[doctype, field, condition, value] rows from FilterGroup.get_filters(), on the doctype's
    own FILTERABLE_FIELDS only; anything else is refused."""
    rows = frappe.parse_json(filters) if isinstance(filters, str) else filters
    if not isinstance(rows, list) or not all(isinstance(f, (list, tuple)) and len(f) >= 4 for f in rows):
        frappe.throw(_("Filters must be a list of [doctype, field, condition, value] rows."))
    allowed = FILTERABLE_FIELDS[doctype]
    for row in rows:
        if row[0] != doctype or row[1] not in allowed:
            frappe.throw(
                _("You can filter {0} on these fields only: {1}").format(_(doctype), ", ".join(sorted(allowed))),
                frappe.PermissionError,
            )
    return [list(f[:4]) for f in rows]


def _enrich_projects(projects, user):
    """Add assignees list and my timesheet stats to each project dict."""
    if not projects:
        return projects

    project_names = [p["name"] for p in projects]
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")

    ToDo = frappe.qb.DocType("ToDo")
    User = frappe.qb.DocType("User")

    assignee_rows = (
        frappe.qb.from_(ToDo)
        .left_join(User)
        .on(User.name == ToDo.allocated_to)
        .select(
            ToDo.reference_name.as_("project"),
            ToDo.allocated_to,
            Coalesce(User.full_name, ToDo.allocated_to).as_("full_name"),
        )
        .where(
            (ToDo.reference_type == "Project")
            & (ToDo.status == "Open")
            & (ToDo.reference_name.isin(project_names))
        )
        .orderby(ToDo.creation)
    ).run(as_dict=True)

    assignees_map = {}
    for row in assignee_rows:
        assignees_map.setdefault(row.project, []).append({
            "user": row.allocated_to,
            "full_name": row.full_name,
            "initial": (row.full_name or row.allocated_to or "?")[0].upper(),
        })

    ts_map = {}
    if employee:
        TimesheetRecord = frappe.qb.DocType("Timesheet Record")

        total_seconds = Sum(
            Case().when(TimesheetRecord.docstatus == 1, TimesheetRecord.actual_time).else_(0)
        )
        billable_seconds = Sum(
            Case().when(
                TimesheetRecord.docstatus != 2,
                billable_seconds_term(TimesheetRecord),
            ).else_(0)
        )

        ts_rows = (
            frappe.qb.from_(TimesheetRecord)
            .select(
                TimesheetRecord.project,
                Count("*").as_("cnt"),
                Coalesce(total_seconds, 0).as_("total_seconds"),
                Coalesce(billable_seconds, 0).as_("billable_seconds"),
                Max(TimesheetRecord.creation).as_("last_used"),
            )
            .where(
                (TimesheetRecord.project.isin(project_names))
                & (TimesheetRecord.employee == employee)
                & (TimesheetRecord.docstatus != 2)
            )
            .groupby(TimesheetRecord.project)
        ).run(as_dict=True)

        ts_map = {
            r.project: {
                "count": r.cnt,
                "total_seconds": int(r.total_seconds),
                "billable_seconds": int(r.billable_seconds),
                "last_used": r.last_used,
            }
            for r in ts_rows
        }

    for p in projects:
        p["assignees"] = assignees_map.get(p["name"], [])
        ts = ts_map.get(p["name"], {"count": 0, "total_seconds": 0, "billable_seconds": 0})
        p["timesheet_count"] = ts["count"]
        p["total_tracked_seconds"] = ts["total_seconds"]
        p["billable_seconds"] = ts["billable_seconds"]
        p["non_billable_seconds"] = max(0, ts["total_seconds"] - ts["billable_seconds"])
        p["last_used"] = ts.get("last_used")
        p["percent_billable"] = percent_billable_preset(p.get("percent_billable"))

    return projects

@frappe.whitelist()
def get_project_timesheets(project_name):
    """Return submitted/draft Timesheet Records for the current employee on a project."""
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        return []
    return frappe.get_all(
        "Timesheet Record",
        filters={"project": project_name, "employee": employee, "docstatus": ["!=", 2]},
        fields=["name", "from_time", "to_time", "actual_time", "goal", "result", "docstatus"],
        order_by="from_time desc",
    )


@frappe.whitelist()
def assign_dev_project(project_name):
    """Assign a project to the current user using Frappe's assignment mechanism."""
    from frappe.desk.form import assign_to as frappe_assign
    frappe_assign.add({
        "doctype": "Project",
        "name": project_name,
        "assign_to": [frappe.session.user],
        "description": f"Assigned to {frappe.session.user} via Developer Action Panel",
    })
    frappe.db.commit()
    return {"project": project_name}


@frappe.whitelist()
def get_active_project_session():
    """Return the active project-based timer (no gitlab_issue) for the current user."""
    user = frappe.session.user
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    if not employee:
        return None

    open_records = frappe.get_all(
        "Timesheet Record",
        filters={"employee": employee, "docstatus": 0, "gitlab_issue": ""},
        fields=["name", "goal", "from_time", "project"],
        order_by="creation desc",
        limit=1,
    )
    if not open_records:
        return None

    record = open_records[0]
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
    session_state = "paused" if last_row.get("to_time") else (
        "running" if last_idx % 2 == 0 else "paused"
    )
    record["session_state"] = session_state
    record["elapsed_seconds"] = _calc_elapsed_seconds(rows)
    record["break_from"] = str(last_row["from_time"]) if session_state == "paused" and not last_row.get("to_time") else None
    record["project_percent_billable"] = billing_context(record["project"])["percent_billable"]
    return record


@frappe.whitelist()
def start_project_timer(project_name, expected_time, goal, manual_start_time=None):
    """Create a project-based Timesheet Record (no GitLab issue)."""
    user = frappe.session.user
    employee = frappe.db.get_value(
        "Employee", {"user_id": user}, ["name", "activity_type"], as_dict=True
    )
    if not employee:
        frappe.throw(_("No Employee record linked to your user account."))

    existing_drafts = frappe.get_all(
        "Timesheet Record",
        filters={"employee": employee.name, "docstatus": 0},
        fields=["name"],
        limit=3,
    )
    if existing_drafts:
        draft_links = ", ".join(
            f'<a href="/app/timesheet-record/{d["name"]}" target="_blank">{d["name"]}</a>'
            for d in existing_drafts[:3]
        )
        frappe.throw(
            _("You already have draft Timesheet Record(s): {0}. "
              "Please submit or cancel them before starting a new timer.").format(draft_links)
        )

    customer = frappe.db.get_value("Project", project_name, "customer")
    start_time = get_datetime(manual_start_time) if manual_start_time else now_datetime()

    ts = frappe.new_doc("Timesheet Record")
    ts.project = project_name
    ts.customer = customer
    ts.employee = employee.name
    ts.activity_type = employee.activity_type
    ts.goal = goal
    ts.expected_time = int(float(expected_time))
    ts.percent_billable = billing_context(project_name)["percent_billable"]
    ts.from_time = start_time
    ts.append("item", {"from_time": start_time})
    ts.insert(ignore_permissions=True)
    frappe.db.commit()

    return {
        "name": ts.name,
        "project": project_name,
        "from_time": str(start_time),
        "session_state": "running",
        "elapsed_seconds": int(time_diff_in_seconds(now_datetime(), start_time)) if manual_start_time else 0,
        "goal": goal,
    }


@frappe.whitelist()
def get_current_employee():
    """Return the Employee record linked to the current user."""
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")


# ---------------------------------------------------------------------------
# Team calendar
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_team_calendar_events():
    """
    Return approved leave applications and team holidays for the team calendar.
    Reuses the same logic as the Project Action Panel calendar.
    """
    from phamos.phamos.page.project_action_panel.project_action_panel import (
        get_employee_leaves,
        get_team_holidays,
    )

    return {
        "leaves": get_employee_leaves(),
        "holidays": get_team_holidays(),
    }


# ---------------------------------------------------------------------------
# My Timesheets
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_my_timesheets(from_date=None, to_date=None, offset=0):
    """
    Return the current employee's Timesheets with project/customer names and
    total billable hours. Used by the Developer Action Panel 'My Timesheets' view.
    """
    employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        return {"timesheets": [], "has_more": False, "offset": offset, "total_on_page": 0}

    offset = int(offset) or 0
    PAGE_SIZE = 500

    Timesheet = frappe.qb.DocType("Timesheet")
    Project = frappe.qb.DocType("Project")
    Customer = frappe.qb.DocType("Customer")
    TimesheetDetail = frappe.qb.DocType("Timesheet Detail")

    conditions = [
        (Timesheet.employee == employee),
        (Timesheet.docstatus != 2)
    ]
    
    # Add date filters if provided (filter by start_date)
    if from_date:
        conditions.append(Timesheet.start_date >= from_date)
    if to_date:
        conditions.append(Timesheet.start_date <= to_date)

    query = (
        frappe.qb.from_(Timesheet)
        .left_join(Project)
        .on(Project.name == Timesheet.parent_project)
        .left_join(Customer)
        .on(Customer.name == Timesheet.customer)
        .left_join(TimesheetDetail)
        .on(TimesheetDetail.parent == Timesheet.name)
        .select(
            Timesheet.name,
            Timesheet.parent_project,
            Timesheet.customer,
            Timesheet.total_hours,
            Timesheet.status,
            Timesheet.creation,
            Timesheet.start_date,
            Timesheet.end_date,
            Timesheet.docstatus,
            Project.project_name,
            Customer.customer_name,
            Coalesce(Sum(TimesheetDetail.billing_hours), 0).as_("billable_hours"),
        )
    )
    
    for condition in conditions:
        query = query.where(condition)
    
    query = (
        query
        .groupby(Timesheet.name)
        .orderby(Timesheet.creation, order=Order.desc)
        .offset(offset)
        .limit(PAGE_SIZE + 1)
    )
    results = query.run(as_dict=True)

    has_more = len(results) > PAGE_SIZE
    if has_more:
        results = results[:PAGE_SIZE]  

    for r in results:
        r["status_label"] = {
            0: "Draft",
            1: "Submitted",
            2: "Cancelled",
        }.get(r.docstatus, r.status)

    first_logs = {}
    names = [r.name for r in results]
    if names:
        for d in frappe.get_all(
            "Timesheet Detail",
            filters={"parent": ["in", names], "idx": 1},
            fields=["parent", "from_time", "to_time"],
        ):
            first_logs[d.parent] = d

    for r in results:
        log = first_logs.get(r.name)
        r["from_time"] = log.from_time if log else None
        r["to_time"] = log.to_time if log else None

    return {
        "timesheets": results,
        "has_more": has_more,
        "offset": offset,
        "total_on_page": len(results),
    }