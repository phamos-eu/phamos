from calendar import month_name
import json
import frappe
from frappe.utils import nowdate


@frappe.whitelist()
def get_gitlab_issue_dashboard_data(projects=None, year=None):
    selected_projects = _normalize_projects(projects)
    year = int(year or nowdate().split("-")[0])

    flow_rows, aging_map, project_names = _build_flow_rows_and_aging(year, selected_projects)
    project_titles = _get_project_titles(project_names)

    return {
        "year": year,
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


def _build_flow_rows_and_aging(year, selected_projects):
    conditions = ["1=1"]
    params = {"year": year}

    if selected_projects:
        conditions.append("gi.gitlab_project IN %(projects)s")
        params["projects"] = tuple(selected_projects)

    project_filter_sql = " AND ".join(conditions)

    opened_rows = frappe.db.sql(
        f"""
        SELECT gi.gitlab_project, MONTH(gi.created_at) AS month_no, COUNT(*) AS opened
        FROM `tabGitLab Issue` gi
        WHERE gi.created_at IS NOT NULL
          AND YEAR(gi.created_at) = %(year)s
          AND {project_filter_sql}
        GROUP BY gi.gitlab_project, MONTH(gi.created_at)
        """,
        params,
        as_dict=True,
    )

    closed_rows = frappe.db.sql(
        f"""
        SELECT gi.gitlab_project, MONTH(gi.closed_at) AS month_no, COUNT(*) AS closed
        FROM `tabGitLab Issue` gi
        WHERE gi.closed_at IS NOT NULL
          AND YEAR(gi.closed_at) = %(year)s
          AND {project_filter_sql}
        GROUP BY gi.gitlab_project, MONTH(gi.closed_at)
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
                    AND YEAR(gi.closed_at) = %(year)s
          AND {project_filter_sql}
        GROUP BY gi.gitlab_project
        """,
        params,
        as_dict=True,
    )

    opened_map = {
        (row.gitlab_project, int(row.month_no)): int(row.opened or 0)
        for row in opened_rows
        if row.month_no
    }
    closed_map = {
        (row.gitlab_project, int(row.month_no)): int(row.closed or 0)
        for row in closed_rows
        if row.month_no
    }

    project_names = _collect_project_names(opened_rows, closed_rows, aging_rows, selected_projects)

    flow_rows = []
    for project in project_names:
        for month_no in range(1, 13):
            opened = opened_map.get((project, month_no), 0)
            closed = closed_map.get((project, month_no), 0)
            flow_balance = round((closed / opened) * 100, 2) if opened else 0

            flow_rows.append(
                {
                    "gitlab_project": project,
                    "month_no": month_no,
                    "month": month_name[month_no],
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
