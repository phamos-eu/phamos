from calendar import month_name
from datetime import date
import json
import frappe
from frappe.utils import getdate, nowdate


@frappe.whitelist()
def get_gitlab_issue_dashboard_data(projects=None, year=None, from_date=None, to_date=None):
    selected_projects = _normalize_projects(projects)
    from_date, to_date = _resolve_date_range(from_date, to_date, year)

    flow_rows, aging_map, project_names = _build_flow_rows_and_aging(from_date, to_date, selected_projects)
    project_titles = _get_project_titles(project_names)

    return {
        "from_date": str(from_date),
        "to_date": str(to_date),
        "projects": selected_projects,
        "project_titles": project_titles,
        "aging": _format_aging_response(aging_map, selected_projects, project_names),
        "monthly_flow": flow_rows,
    }


def _normalize_projects(projects):
    if not projects:
        return []

    if isinstance(projects, list):
        normalized = []
        for item in projects:
            if isinstance(item, dict):
                value = item.get("value") or item.get("name")
                if value:
                    normalized.append(value)
            elif item:
                normalized.append(item)
        return normalized

    if isinstance(projects, str):
        projects = projects.strip()
        if not projects:
            return []

        if projects.startswith("["):
            try:
                parsed = json.loads(projects)
                return _normalize_projects(parsed)
            except Exception:
                pass

        parts = [p.strip() for p in projects.split(",")]
        return [p for p in parts if p]

    return []


def _resolve_date_range(from_date, to_date, year):
    if from_date and to_date:
        start_date = getdate(from_date)
        end_date = getdate(to_date)

    elif year:
        year = int(year)
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)

    else:
        end_date = getdate(nowdate())
        start_date = _shift_months(end_date, -6)

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    return start_date, end_date


def _shift_months(input_date, months):
    month_index = input_date.month - 1 + months
    year = input_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(input_date.day, 28)
    return date(year, month, day)


def _month_sequence(start_date, end_date):
    year, month = start_date.year, start_date.month
    end_year, end_month = end_date.year, end_date.month
    sequence = []

    while (year, month) <= (end_year, end_month):
        sequence.append((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1

    return sequence


def _build_flow_rows_and_aging(from_date, to_date, selected_projects):
    conditions = ["1=1"]
    params = {
        "from_date": from_date,
        "to_date": to_date,
    }

    if selected_projects:
        conditions.append("gi.gitlab_project IN %(projects)s")
        params["projects"] = tuple(selected_projects)

    project_filter_sql = " AND ".join(conditions)

    opened_rows = frappe.db.sql(
        f"""
                SELECT
                        gi.gitlab_project,
                        YEAR(gi.created_at) AS year_no,
                        MONTH(gi.created_at) AS month_no,
                        COUNT(*) AS opened
        FROM `tabGitLab Issue` gi
        WHERE gi.created_at IS NOT NULL
                    AND DATE(gi.created_at) BETWEEN %(from_date)s AND %(to_date)s
          AND {project_filter_sql}
                GROUP BY gi.gitlab_project, YEAR(gi.created_at), MONTH(gi.created_at)
        """,
        params,
        as_dict=True,
    )

    closed_rows = frappe.db.sql(
        f"""
                SELECT
                        gi.gitlab_project,
                        YEAR(gi.closed_at) AS year_no,
                        MONTH(gi.closed_at) AS month_no,
                        COUNT(*) AS closed
        FROM `tabGitLab Issue` gi
        WHERE gi.closed_at IS NOT NULL
                    AND DATE(gi.closed_at) BETWEEN %(from_date)s AND %(to_date)s
          AND {project_filter_sql}
                GROUP BY gi.gitlab_project, YEAR(gi.closed_at), MONTH(gi.closed_at)
        """,
        params,
        as_dict=True,
    )

    aging_rows = frappe.db.sql(
        f"""
        SELECT
            gi.gitlab_project,
                        SUM(CASE WHEN DATEDIFF(DATE(gi.closed_at), DATE(gi.created_at)) <= 30 THEN 1 ELSE 0 END) AS bucket_0_30,
                        SUM(CASE WHEN DATEDIFF(DATE(gi.closed_at), DATE(gi.created_at)) > 30 AND DATEDIFF(DATE(gi.closed_at), DATE(gi.created_at)) <= 90 THEN 1 ELSE 0 END) AS bucket_31_90,
                        SUM(CASE WHEN DATEDIFF(DATE(gi.closed_at), DATE(gi.created_at)) > 90 THEN 1 ELSE 0 END) AS bucket_gt_90
        FROM `tabGitLab Issue` gi
        WHERE gi.state = 'closed'
          AND gi.created_at IS NOT NULL
                    AND gi.closed_at IS NOT NULL
                    AND DATE(gi.closed_at) BETWEEN %(from_date)s AND %(to_date)s
          AND {project_filter_sql}
        GROUP BY gi.gitlab_project
        """,
        params,
        as_dict=True,
    )

    opened_map = {
        (row.gitlab_project, int(row.year_no), int(row.month_no)): int(row.opened or 0)
        for row in opened_rows
        if row.month_no and row.year_no
    }
    closed_map = {
        (row.gitlab_project, int(row.year_no), int(row.month_no)): int(row.closed or 0)
        for row in closed_rows
        if row.month_no and row.year_no
    }

    project_names = _collect_project_names(opened_rows, closed_rows, aging_rows, selected_projects)
    months = _month_sequence(from_date, to_date)

    flow_rows = []
    for project in project_names:
        for index, (year_no, month_no) in enumerate(months, start=1):
            opened = opened_map.get((project, year_no, month_no), 0)
            closed = closed_map.get((project, year_no, month_no), 0)
            flow_balance = round((closed / opened) * 100, 2) if opened else 0

            flow_rows.append(
                {
                    "gitlab_project": project,
                    "month_key": f"{year_no}-{month_no:02d}",
                    "year_no": year_no,
                    "month_no": month_no,
                    "month_order": index,
                    "month": f"{month_name[month_no]} {year_no}",
                    "opened": opened,
                    "closed": closed,
                    "flow_balance": flow_balance,
                }
            )

    aging_map = {
        row.gitlab_project: {
            "bucket_0_30": int(row.bucket_0_30 or 0),
            "bucket_31_90": int(row.bucket_31_90 or 0),
            "bucket_gt_90": int(row.bucket_gt_90 or 0),
        }
        for row in aging_rows
    }

    return flow_rows, aging_map, project_names


def _collect_project_names(opened_rows, closed_rows, aging_rows, selected_projects):
    if selected_projects:
        return selected_projects

    names = set()
    for row in opened_rows:
        names.add(row.gitlab_project)
    for row in closed_rows:
        names.add(row.gitlab_project)
    for row in aging_rows:
        names.add(row.gitlab_project)

    return sorted(names)


def _get_project_titles(project_names):
    if not project_names:
        return {}

    rows = frappe.get_all(
        "GitLab Project",
        filters={"name": ["in", project_names]},
        fields=["name", "title"],
        limit_page_length=0,
    )

    title_map = {}
    for row in rows:
        title_map[row.name] = row.title or row.name

    for name in project_names:
        if name not in title_map:
            title_map[name] = name

    return title_map


def _format_aging_response(aging_map, selected_projects, project_names):
    compare_projects = selected_projects or project_names
    project_buckets = []

    for project in compare_projects:
        values = aging_map.get(
            project,
            {"bucket_0_30": 0, "bucket_31_90": 0, "bucket_gt_90": 0},
        )
        project_buckets.append(
            {
                "project": project,
                "bucket_0_30": values["bucket_0_30"],
                "bucket_31_90": values["bucket_31_90"],
                "bucket_gt_90": values["bucket_gt_90"],
            }
        )

    if len(selected_projects) == 1 and selected_projects[0] in aging_map:
        project = selected_projects[0]
        values = aging_map[project]
        return {
            "mode": "single",
            "project": project,
            "bucket_0_30": values["bucket_0_30"],
            "bucket_31_90": values["bucket_31_90"],
            "bucket_gt_90": values["bucket_gt_90"],
            "project_buckets": project_buckets,
        }

    if len(selected_projects) > 1:
        total_0_30 = sum(v["bucket_0_30"] for v in aging_map.values())
        total_31_90 = sum(v["bucket_31_90"] for v in aging_map.values())
        total_gt_90 = sum(v["bucket_gt_90"] for v in aging_map.values())

        return {
            "mode": "project_compare",
            "project": None,
            "bucket_0_30": total_0_30,
            "bucket_31_90": total_31_90,
            "bucket_gt_90": total_gt_90,
            "project_buckets": project_buckets,
        }

    total_0_30 = sum(v["bucket_0_30"] for v in aging_map.values())
    total_31_90 = sum(v["bucket_31_90"] for v in aging_map.values())
    total_gt_90 = sum(v["bucket_gt_90"] for v in aging_map.values())

    return {
        "mode": "combined",
        "project": None,
        "bucket_0_30": total_0_30,
        "bucket_31_90": total_31_90,
        "bucket_gt_90": total_gt_90,
        "project_buckets": project_buckets,
    }
