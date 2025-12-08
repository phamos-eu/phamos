import frappe
from datetime import datetime, timedelta, date

@frappe.whitelist()
def get_team_capacity(filters=None):
    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    selected_team = filters.get("team") or []

    if not from_date or not to_date:
        frappe.throw("Please select both From Date and To Date.")

    # Convert to datetime.date
    from_dt = datetime.strptime(from_date, "%Y-%m-%d").date()
    to_dt = datetime.strptime(to_date, "%Y-%m-%d").date()

    # Generate weekly ranges
    week_buckets = generate_weeks(from_dt, to_dt)
    week_labels = [f"{w['start'].strftime('%Y-%m-%d')} to {w['end'].strftime('%Y-%m-%d')}" for w in week_buckets]

    # Fetch all Ledger entries in range
    conditions = ["date >= %s", "date <= %s"]
    values = [from_date, to_date]
    if selected_team:
        placeholders = ", ".join(["%s"] * len(selected_team))
        conditions.append(f"team IN ({placeholders})")
        values.extend(selected_team)

    entries = frappe.db.sql(f"""
        SELECT team, total_team_capacity, date
        FROM `tabTeam Capacity Ledger`
        WHERE {" AND ".join(conditions)}
        ORDER BY team, date
    """, values, as_dict=1)

    # Fetch default Team capacities (fallback)
    teams_default = frappe.get_all("Team", fields=["name", "total_team_capacity"])
    if selected_team:
        teams_default = [t for t in teams_default if t.name in selected_team]

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

    # Convert to list for chart
    teams = []
    colors = ["#7cb5ec", "#434348", "#90ed7d", "#f7a35c", "#8085e9", "#f15c80"]
    for i, (team_name, data) in enumerate(teams_dict.items()):
        teams.append({
            "name": team_name,
            "data": data,
            "color": colors[i % len(colors)]
        })

    # Actual line
    actual_line = []
    for w in week_buckets:
        week_start = w["start"].date() if isinstance(w["start"], datetime) else w["start"]
        week_end = w["end"].date() if isinstance(w["end"], datetime) else w["end"]

        s = week_start.strftime("%Y-%m-%d") + " 00:00:00"
        e = week_end.strftime("%Y-%m-%d") + " 23:59:59"

        total_actual = frappe.db.sql("""
            SELECT SUM(actual_time)
            FROM `tabTimesheet Record`
            WHERE from_time <= %s AND to_time >= %s
        """, (e, s))[0][0] or 0

        actual_line.append(round(total_actual / 3600, 2))

    return {
        "weeks": week_labels,
        "teams": teams,
        "actual_line": actual_line
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
