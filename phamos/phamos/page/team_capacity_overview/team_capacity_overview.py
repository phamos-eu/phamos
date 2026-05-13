import frappe
from frappe.query_builder import DocType
from frappe.query_builder.functions import Sum, Avg, Count
from pypika import Criterion
from datetime import datetime, timedelta, date

@frappe.whitelist()
def get_team_capacity(filters=None):
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    selected_team = filters.get("team") or []
    enable_comparison = filters.get("enable_comparison")
    comparison_type = filters.get("comparison_type")

    # FIX 1: string vs list
    if isinstance(selected_team, str):
        selected_team = [selected_team] if selected_team else []

    # FIX 2: "0" string truthy bug
    enable_comparison = frappe.utils.cint(enable_comparison)

    if not from_date or not to_date:
        frappe.throw("Please select both From Date and To Date.")

    # Convert to datetime.date
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

    # Generate weekly ranges
    week_buckets = generate_weeks(from_dt, to_dt)
    week_labels = [
        f"{w['start'].strftime('%Y-%m-%d')} to {w['end'].strftime('%Y-%m-%d')}"
        for w in week_buckets
    ]

    # ── Fetch Ledger entries via QueryBuilder ──
    Ledger = DocType("Team Capacity Ledger")
    ledger_query = (
        frappe.qb.from_(Ledger)
        .select(Ledger.team, Ledger.total_team_capacity, Ledger.date)
        .where(Ledger.date >= from_date)
        .where(Ledger.date <= to_date)
        .orderby(Ledger.team)
        .orderby(Ledger.date)
    )
    if selected_team:
        ledger_query = ledger_query.where(Ledger.team.isin(selected_team))

    entries = ledger_query.run(as_dict=True)

    # ── Fetch default Team capacities via QueryBuilder ──
    Team = DocType("Team")
    team_query = (
        frappe.qb.from_(Team)
        .select(Team.name, Team.total_team_capacity)
    )
    if selected_team:
        team_query = team_query.where(Team.name.isin(selected_team))

    teams_default = team_query.run(as_dict=True)

    # Prepare team-week capacities
    teams_dict = {}
    for t in teams_default:
        teams_dict[t["name"]] = [t["total_team_capacity"] or 0] * len(week_buckets)

    # Apply Ledger entries with carry-forward logic
    # Organize entries by team
    entries_by_team = {}
    for e in entries:
        team = e.team
        entry_date = e.date
        if isinstance(entry_date, datetime):
            entry_date = entry_date.date()
        if team not in entries_by_team:
            entries_by_team[team] = []
        entries_by_team[team].append((entry_date, e.total_team_capacity or 0))

    for team, week_data in teams_dict.items():
        last_capacity = week_data[0]  # start with default team capacity

        if team in entries_by_team:
            ledger_entries = sorted(entries_by_team[team], key=lambda x: x[0])

            for idx, w in enumerate(week_buckets):
                week_start = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
                week_end = w["end"].date() if isinstance(w["end"], datetime) else w["end"]

                # Collect all entries for this week
                week_caps = [cap for (d, cap) in ledger_entries if week_start <= d <= week_end]

                if week_caps:
                    # Average for this week
                    avg_cap = sum(week_caps) / len(week_caps)
                    week_data[idx] = round(avg_cap, 2)
                    last_capacity = week_data[idx]
                else:
                    # No entries → use last known capacity
                    week_data[idx] = last_capacity
        else:
            continue

    # ── DocTypes for Timesheet queries ──
    TS   = DocType("Timesheet")
    Proj = DocType("Project")
    Impl = DocType("Implementation")

    # ── Helper: fetch actual hours for a team + date range ──
    def get_actual_hours(week_start_str, week_end_str, team_name=None, team_list=None):
        """
        Returns total hours from tabTimesheet for the given date range.
        - Uses start_date (DATE field) — no time suffix needed.
        - total_hours is already in hours, so NO /3600 division.
        - Filters by team via Implementation join.
        """
        q = (
            frappe.qb.from_(TS)
            .left_join(Proj).on(Proj.name == TS.parent_project)
            .left_join(Impl).on(Impl.name == Proj.custom_implementation)
            .select(Sum(TS.total_hours))
            .where(TS.start_date >= week_start_str)
            .where(TS.start_date <= week_end_str)
            .where(TS.docstatus != 2)
        )
        if team_name:
            q = q.where(Impl.team == team_name)
        elif team_list:
            q = q.where(Impl.team.isin(team_list))

        result = q.run()
        return round(float(result[0][0] or 0), 2)

    # ── Convert to list for chart ──
    colors = ["#7cb5ec", "#F30BE7", "#90ed7d", "#f7a35c", "#8085e9", "#f15c80"]
    teams = []

    for i, (team_name, data) in enumerate(teams_dict.items()):

        # ── Current Team Actual Time ──
        actual_data = []

        for w in week_buckets:
            ws = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
            we = w["end"].date() if isinstance(w["end"], datetime) else w["end"]
            actual_data.append(
                get_actual_hours(ws.strftime("%Y-%m-%d"), we.strftime("%Y-%m-%d"), team_name=team_name)
            )

        # ── Historical Team Actual Time ──
        historical_actual_data = []

        if enable_comparison:

            hist_start, hist_end = shift_period(from_dt, to_dt, comparison_type)

            if hist_start and hist_end:

                hist_weeks = generate_weeks(hist_start, hist_end)

                for w in hist_weeks:
                    ws = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
                    we = w["end"].date() if isinstance(w["end"], datetime) else w["end"]
                    historical_actual_data.append(
                        get_actual_hours(ws.strftime("%Y-%m-%d"), we.strftime("%Y-%m-%d"), team_name=team_name)
                    )

        teams.append({
            "name": team_name,
            "data": data,
            "actual_data": actual_data,
            "historical_actual_data": historical_actual_data,
            "color": colors[i % len(colors)]
        })

    # ── Overall actual_line (all selected teams combined) ──
    actual_line = []
    for w in week_buckets:
        ws = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
        we = w["end"].date() if isinstance(w["end"], datetime) else w["end"]
        actual_line.append(
            get_actual_hours(
                ws.strftime("%Y-%m-%d"),
                we.strftime("%Y-%m-%d"),
                team_list=selected_team if selected_team else None
            )
        )

    # ── Historical actual_line ──
    historical_actual_line = None

    if enable_comparison:
        hist_start, hist_end = shift_period(from_dt, to_dt, comparison_type)

        if not hist_start or not hist_end:
            frappe.msgprint("Invalid comparison type selected.", alert=True)
        else:
            # Check if hist data exists via QueryBuilder
            hist_count_q = (
                frappe.qb.from_(TS)
                .select(Count("*"))
                .where(TS.start_date >= str(hist_start))
                .where(TS.start_date <= str(hist_end))
                .where(TS.docstatus != 2)
            )
            hist_count = hist_count_q.run()[0][0]

            if hist_count == 0:
                frappe.msgprint(
                    f"No data found for comparison period ({hist_start} to {hist_end}).",
                    alert=True
                )
            else:
                hist_weeks = generate_weeks(hist_start, hist_end)
                historical_actual_line = []

                for w in hist_weeks:
                    ws = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
                    we = w["end"].date() if isinstance(w["end"], datetime) else w["end"]
                    historical_actual_line.append(
                        get_actual_hours(
                            ws.strftime("%Y-%m-%d"),
                            we.strftime("%Y-%m-%d"),
                            team_list=selected_team if selected_team else None
                        )
                    )

    return {
        "weeks": week_labels,
        "teams": teams,
        "actual_line": actual_line,
        "historical_actual_line": historical_actual_line,
    }

def generate_weeks(start_date, end_date):
    weeks = []
    current = start_date
    while current <= end_date:
        week_start = current
        week_end = min(current + timedelta(days=6), end_date)
        weeks.append({"start": week_start, "end": week_end})
        current = week_end + timedelta(days=1)
    return weeks


# FIX 4: leap year + last_month safe shift
def safe_replace_year(d, year):
    try:
        return d.replace(year=year)
    except ValueError:
        # Feb 29 edge case - use Feb 28
        return d.replace(year=year, day=28)

def shift_period(start, end, comparison_type):
    if comparison_type == "last_year":
        return (
            safe_replace_year(start, start.year - 1),
            safe_replace_year(end, end.year - 1),
        )

    elif comparison_type == "last_month":
        first_of_start = start.replace(day=1)
        prev_month_end = first_of_start - timedelta(days=1)
        try:
            shifted_start = prev_month_end.replace(day=start.day)
        except ValueError:
            shifted_start = prev_month_end

        first_of_end = end.replace(day=1)
        prev_month_end2 = first_of_end - timedelta(days=1)
        try:
            shifted_end = prev_month_end2.replace(day=end.day)
        except ValueError:
            shifted_end = prev_month_end2

        return shifted_start, shifted_end

    return None, None

@frappe.whitelist()
def get_all_teams(txt="", **kwargs):
    Team = DocType("Team")
    result = (
        frappe.qb.from_(Team)
        .select(Team.name)
        .where(Team.name.like(f"%{txt}%"))
        .orderby(Team.name)
        .limit(50)
    ).run(as_dict=True)
    return [t.name for t in result]