# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab and SLA statistics of a Team (#1976): team totals only, no figures per person.

Which GitLab items count (decisions 2 and 3 of #1976): an item counts for the team when its
assignee is one of the team's people. The assignee's email (`GitLab Issue.assignee_email`) is
matched to the Employee's user, company email or personal email, and that Employee must have been
in the team (Team Assignment, #1974) on the item's date: the closing date for closed items, the
creation date for opened items, today for open items. So items count wherever the person works.
A proper GitLab user link beyond email is #2227.

Each figure is split by the item's project:
- own: the project's Implementation belongs to this team
- other: another Implementation
- internal: no Implementation

Kinds of items: a parent item is one that other items point to (`parent_issue`); every other item
is a work item. Closing times are given for both.

The Gitlab Issue Dashboard (Desk page) filters by project, not by person, so its figures are not
reused here.

SLA figures (decision 4): the team's Issues (Team field, or a project of the team's
Implementations), only while SLA tracking is on in Support Settings.
"""

from datetime import timezone
from statistics import median
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import add_months, get_datetime, get_first_day, get_last_day, get_system_timezone, getdate

from phamos.cockpits import teams
from phamos.cockpits.team_hours import month_windows
from phamos.phamos.doctype.team_assignment.team_assignment import members_between

GROUPS = ("own", "other", "internal")


def _emails_by_employee(employees):
	"""{lowercase email: employee} from the user, company and personal email of each Employee."""
	emails = {}
	for row in frappe.get_all(
		"Employee",
		filters={"name": ["in", list(employees)]},
		fields=["name", "user_id", "company_email", "personal_email"],
	):
		for email in (row.user_id, row.company_email, row.personal_email):
			if email:
				emails.setdefault(email.strip().lower(), row.name)
	return emails


def _all_employee_emails():
	"""Every email any Employee has: to tell 'nobody we know' from 'someone in another team'."""
	known = set()
	for row in frappe.get_all("Employee", fields=["user_id", "company_email", "personal_email"]):
		known.update(e.strip().lower() for e in (row.user_id, row.company_email, row.personal_email) if e)
	return known


def _system_time(utc_value):
	"""The sync stores GitLab times as naive UTC (gitlab_utils._parse_gitlab_datetime); dates and
	ages are taken in the system time zone, so an item closed at 00:30 on 1 March counts in March."""
	if not utc_value:
		return None
	return (
		get_datetime(utc_value)
		.replace(tzinfo=timezone.utc)
		.astimezone(ZoneInfo(get_system_timezone()))
		.replace(tzinfo=None)
	)


def _in_team(periods, day):
	return any(start <= day <= end for start, end in periods)


def _project_groups(team):
	"""{GitLab Project: group} and the set of the team's own GitLab Projects."""
	implementation_team = dict(frappe.get_all("Implementation", fields=["name", "team"], as_list=True))
	groups, own = {}, set()
	for project, implementation in frappe.get_all("GitLab Project", fields=["name", "implementation"], as_list=True):
		if not implementation:
			groups[project] = "internal"
		elif implementation_team.get(implementation) == team:
			groups[project] = "own"
			own.add(project)
		else:
			groups[project] = "other"
	return groups, own


def _items(range_start):
	"""GitLab Issues that matter for [range_start, today]: created or closed since then, or open.
	`range_start` is a system-time date; the stored times are UTC, so the filter is converted."""
	from phamos.gitlab_integration.issue_refs import _system_to_utc

	range_start = _system_to_utc(get_datetime(range_start))
	rows = frappe.db.sql(
		"""
		select gi.name, gi.state, gi.created_at, gi.closed_at, gi.assignee_email, gi.parent_issue,
			gi.gitlab_project, count(c.name) as comments
		from `tabGitLab Issue` gi
		left join `tabGitLab Issue Comment` c on c.parent = gi.name and c.parenttype = 'GitLab Issue'
		where gi.created_at >= %(start)s or gi.closed_at >= %(start)s or gi.state = 'opened'
		group by gi.name
		""",
		{"start": range_start},
		as_dict=True,
	)
	# every item some other item points to, also when that child is older than the range
	parents = set(
		frappe.get_all("GitLab Issue", filters={"parent_issue": ["is", "set"]}, pluck="parent_issue", distinct=True)
	)
	for row in rows:
		row.is_parent = row.name in parents
	return rows


def _days_between(start, end):
	return (get_datetime(end) - get_datetime(start)).total_seconds() / 86400


def _summary(values):
	if not values:
		return {"average": None, "median": None, "count": 0}
	return {"average": round(sum(values) / len(values), 1), "median": round(median(values), 1), "count": len(values)}


def _window(items, start, end):
	"""Figures for the items opened or closed in [start, end] (already filtered to the team)."""
	closed = [i for i in items if i.closed_on and start <= i.closed_on <= end and i.counts_closed]
	opened = [i for i in items if start <= i.created_on <= end and i.counts_opened]
	return frappe._dict(
		start=start,
		end=end,
		closed={group: sum(1 for i in closed if i.group == group) for group in GROUPS},
		opened={group: sum(1 for i in opened if i.group == group) for group in GROUPS},
		closed_total=len(closed),
		opened_total=len(opened),
		work_item_days=_summary([i.closing_days for i in closed if not i.is_parent]),
		parent_item_days=_summary([i.closing_days for i in closed if i.is_parent]),
		comments_per_closed_item=round(sum(i.comments for i in closed) / len(closed), 1) if closed else None,
	)


def _merge_requests(range_start, emails, periods, groups):
	"""The team's merge requests (#1977): by the author's email, member on the merge date (the
	creation date for opened ones), wherever they work; times in system time like the items."""
	from phamos.gitlab_integration.issue_refs import _system_to_utc

	if not frappe.db.table_exists("GitLab Merge Request"):
		return []
	start_utc = _system_to_utc(get_datetime(range_start))
	rows = frappe.get_all(
		"GitLab Merge Request",
		or_filters=[["created_at", ">=", start_utc], ["merged_at", ">=", start_utc]],
		fields=["gitlab_project", "author_email", "created_at", "merged_at", "lines_added", "lines_removed"],
		limit_page_length=0,
	)
	team_rows = []
	for row in rows:
		employee = emails.get((row.author_email or "").strip().lower())
		if not employee or not row.created_at:
			continue
		row.created_at = _system_time(row.created_at)
		row.merged_at = _system_time(row.merged_at)
		row.created_on = getdate(row.created_at)
		row.merged_on = getdate(row.merged_at) if row.merged_at else None
		row.group = groups.get(row.gitlab_project, "internal")
		row.counts_opened = _in_team(periods[employee], row.created_on)
		row.counts_merged = bool(row.merged_on) and _in_team(periods[employee], row.merged_on)
		if row.counts_opened or row.counts_merged:
			team_rows.append(row)
	return team_rows


def _merge_request_window(rows, start, end):
	merged = [r for r in rows if r.counts_merged and start <= r.merged_on <= end]
	return frappe._dict(
		merged={group: sum(1 for r in merged if r.group == group) for group in GROUPS},
		merged_total=len(merged),
		# lines of the merge requests merged in the period: what reached the code base
		lines_added={group: sum(r.lines_added or 0 for r in merged if r.group == group) for group in GROUPS},
		lines_removed={group: sum(r.lines_removed or 0 for r in merged if r.group == group) for group in GROUPS},
		days_to_merge=_summary([_days_between(r.created_at, r.merged_at) for r in merged]),
	)


def _sla(team, windows):
	"""SLA figures of the team's Issues per window, or None while SLA tracking is off."""
	if not frappe.db.get_single_value("Support Settings", "track_service_level_agreement"):
		return None
	projects = teams.team_projects(team)
	or_filters = [["custom_team", "=", team]]
	if projects:
		or_filters.append(["project", "in", projects])
	result = {}
	for key, (start, end) in windows.items():
		responded = frappe.get_all(
			"Issue",
			filters={"first_responded_on": ["between", [f"{start} 00:00:00", f"{end} 23:59:59"]]},
			or_filters=or_filters,
			fields=["first_response_time", "first_responded_on", "response_by"],
		)
		with_target = [r for r in responded if r.response_by]
		resolved = frappe.get_all(
			"Issue",
			filters={"opening_date": ["between", [start, end]], "agreement_status": ["in", ["Fulfilled", "Failed"]]},
			or_filters=or_filters,
			fields=["agreement_status"],
		)
		result[key] = frappe._dict(
			responses=len(responded),
			first_response_hours=round(
				sum(r.first_response_time or 0 for r in responded) / len(responded) / 3600, 1
			)
			if responded
			else None,
			responses_in_time=round(
				sum(1 for r in with_target if r.first_responded_on <= r.response_by) / len(with_target) * 100, 1
			)
			if with_target
			else None,
			resolutions=len(resolved),
			resolutions_in_time=round(sum(1 for r in resolved if r.agreement_status == "Fulfilled") / len(resolved) * 100, 1)
			if resolved
			else None,
		)
	return result


def team_gitlab_statistics(team, today=None):
	"""Everything the GitLab page shows: windows with comparisons, 12 months of closed items, open
	item age, the count of unmatched items in the team's own projects, and the SLA figures."""
	today = getdate(today)
	range_start = get_first_day(add_months(today, -12))
	periods = members_between(team, range_start, today)
	emails = _emails_by_employee(periods)
	known_emails = _all_employee_emails()
	groups, own_projects = _project_groups(team)

	month_start = get_first_day(today)
	team_items, unmatched = [], 0
	for item in _items(range_start):
		if not item.created_at:
			# a time the sync could not parse: no date to count it on
			continue
		item.created_at = _system_time(item.created_at)
		item.closed_at = _system_time(item.closed_at)
		item.created_on = getdate(item.created_at)
		item.closed_on = getdate(item.closed_at) if item.closed_at else None
		email = (item.assignee_email or "").strip().lower()
		employee = emails.get(email)
		item.group = groups.get(item.gitlab_project, "internal")
		if not employee:
			# the notice: open items and items closed this month in the team's own projects whose
			# assignee is nobody we know; unassigned items are not a matching problem
			recent = item.state == "opened" or (item.closed_on and item.closed_on >= month_start)
			if email and recent and item.gitlab_project in own_projects and email not in known_emails:
				unmatched += 1
			continue
		member_periods = periods[employee]
		item.counts_opened = _in_team(member_periods, item.created_on)
		item.counts_closed = item.state == "closed" and bool(item.closed_on) and _in_team(member_periods, item.closed_on)
		item.counts_open = item.state == "opened" and _in_team(member_periods, today)
		if item.closed_at:
			item.closing_days = _days_between(item.created_at, item.closed_at)
		if item.counts_opened or item.counts_closed or item.counts_open:
			team_items.append(item)

	merge_requests = _merge_requests(range_start, emails, periods, groups)
	windows = month_windows(today)
	open_items = [i for i in team_items if i.counts_open]
	open_ages = [(today - i.created_on).days for i in open_items]
	months = []
	for offset in range(11, -1, -1):
		start = get_first_day(add_months(today, -offset))
		end = min(getdate(get_last_day(start)), today)
		window = _window(team_items, start, end)
		mr_window = _merge_request_window(merge_requests, start, end)
		months.append(
			frappe._dict(
				start=start,
				closed=window.closed,
				opened_total=window.opened_total,
				lines_added=mr_window.lines_added,
				lines_removed=mr_window.lines_removed,
				merged_total=mr_window.merged_total,
				mtd=end < getdate(get_last_day(start)),
			)
		)

	return frappe._dict(
		today=today,
		windows={key: _window(team_items, start, end) for key, (start, end) in windows.items()},
		merge_requests={key: _merge_request_window(merge_requests, start, end) for key, (start, end) in windows.items()},
		months=months,
		open_items=frappe._dict(
			count=len(open_items),
			by_group={group: sum(1 for i in open_items if i.group == group) for group in GROUPS},
			median_age_days=round(median(open_ages), 1) if open_ages else None,
			oldest_age_days=max(open_ages) if open_ages else None,
		),
		unmatched_own_items=unmatched,
		sla=_sla(team, windows),
	)
