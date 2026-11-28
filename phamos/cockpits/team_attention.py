# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit "Needs attention" (#2235): the team's open Issues and Tasks that lie around, and
Issues whose SLA was missed or is due soon. A list of records for the team as a whole, never a
figure per person (decision 3 of #1954).

Each item carries `since`: the moment it started to need attention (last activity + idle days, an
SLA deadline, or the deadline minus the "due soon" window). The morning summary posts only items
whose `since` lies in the last day, so the same item is not announced twice and a quiet day posts
nothing. No state is kept.
"""

import json
from datetime import timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, escape_html, get_datetime, get_url, now_datetime

from phamos.cockpits import teams

DEFAULT_IDLE_DAYS = 10
DEFAULT_SLA_DUE_HOURS = 24
SUMMARY_WINDOW = timedelta(days=1)
SUMMARY_MAX_ITEMS = 15

OPEN_STATUS = {
	# Issue statuses that are done; Task statuses that are done or not real work
	"Issue": ["Resolved", "Closed"],
	"Task": ["Completed", "Cancelled", "Template"],
}


def _settings():
	from phamos.cockpits.settings import COCKPIT_SETTINGS

	idle = cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "team_attention_idle_days")) or DEFAULT_IDLE_DAYS
	due = cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "team_attention_sla_due_hours")) or DEFAULT_SLA_DUE_HOURS
	return idle, due


def sla_on():
	return bool(frappe.db.get_single_value("Support Settings", "track_service_level_agreement"))


def _team_or_filters(team):
	"""The team's records: named on the record, or in a Project of the team's Implementations."""
	or_filters = [["custom_team", "=", team]]
	projects = teams.team_projects(team)
	if projects:
		or_filters.append(["project", "in", projects])
	return or_filters


def _open_records(doctype, team, fields):
	return frappe.get_all(
		doctype,
		filters=[["status", "not in", OPEN_STATUS[doctype]]],
		or_filters=_team_or_filters(team),
		fields=["name", "modified", "creation", "_assign", *fields],
		limit_page_length=0,
	)


def _latest_reference(table, doctype, names):
	"""{name: latest creation} of the Comments or Communications on `names`."""
	if not names:
		return {}
	rows = frappe.get_all(
		table,
		filters={"reference_doctype": doctype, "reference_name": ["in", names]},
		fields=["reference_name", "max(creation) as latest"],
		group_by="reference_name",
	)
	return {r.reference_name: r.latest for r in rows}


def _latest(sql, names):
	"""{name: latest datetime} from a grouped query over `names`."""
	if not names:
		return {}
	return {row[0]: row[1] for row in frappe.db.sql(sql, {"names": tuple(names)})}


def _last_activity(doctype, rows):
	"""{name: last change, comment, mail or timesheet}."""
	names = [r.name for r in rows]
	latest = {r.name: get_datetime(r.modified) for r in rows}
	sources = [_latest_reference(table, doctype, names) for table in ("Comment", "Communication")]
	if doctype == "Task":
		sources.append(
			_latest(
				"""select td.task, max(td.from_time) from `tabTimesheet Detail` td
				join `tabTimesheet` t on t.name = td.parent and t.docstatus < 2
				where td.task in %(names)s group by td.task""",
				names,
			)
		)
	for source in sources:
		for name, when in source.items():
			if when and get_datetime(when) > latest[name]:
				latest[name] = get_datetime(when)
	return latest


def _assignees(raw):
	try:
		users = json.loads(raw or "[]")
	except ValueError:
		users = []
	return [frappe.utils.get_fullname(u) for u in users]


def _item(doctype, row, title, kind, since, detail):
	return frappe._dict(
		doctype=doctype,
		name=row.name,
		title=title,
		kind=kind,
		since=since,
		detail=detail,
		assignees=_assignees(row._assign),
	)


def idle_items(team, now=None):
	"""Open Issues and Tasks of the team with no change, comment, mail or timesheet for N days."""
	now = get_datetime(now or now_datetime())
	idle_days, _due = _settings()
	limit = now - timedelta(days=idle_days)
	found = []
	for doctype, title_field in (("Issue", "subject"), ("Task", "subject")):
		rows = _open_records(doctype, team, [title_field])
		activity = _last_activity(doctype, rows)
		for row in rows:
			last = activity.get(row.name) or get_datetime(row.creation)
			if last <= limit:
				days = (now - last).days
				found.append(
					_item(doctype, row, row.get(title_field), "idle", last + timedelta(days=idle_days), _("No activity for {0} days").format(days))
				)
	return found


def sla_items(team, now=None):
	"""Open Issues of the team whose SLA response or resolution was missed or is due soon; only
	while SLA tracking is on (decision 2 of #1981)."""
	if not sla_on():
		return []
	now = get_datetime(now or now_datetime())
	_idle, due_hours = _settings()
	window = timedelta(hours=due_hours)
	found = []
	for row in _open_records("Issue", team, ["subject", "response_by", "first_responded_on", "sla_resolution_by", "sla_resolution_date"]):
		item = None
		if row.response_by and not row.first_responded_on:
			deadline = get_datetime(row.response_by)
			if deadline <= now:
				item = _item("Issue", row, row.subject, "response_missed", deadline, _("First response missed"))
			elif deadline - window <= now:
				item = _item("Issue", row, row.subject, "response_due", deadline - window, _("First response due"))
		if not item and row.sla_resolution_by and not row.sla_resolution_date:
			deadline = get_datetime(row.sla_resolution_by)
			if deadline <= now:
				item = _item("Issue", row, row.subject, "resolution_missed", deadline, _("Resolution missed"))
			elif deadline - window <= now:
				item = _item("Issue", row, row.subject, "resolution_due", deadline - window, _("Resolution due"))
		if item:
			item.deadline = deadline
			found.append(item)
	return found


def attention_items(team, now=None):
	"""SLA items first (most urgent first), then idle records (longest idle first)."""
	sla = sorted(sla_items(team, now), key=lambda i: i.deadline)
	listed = {(i.doctype, i.name) for i in sla}
	idle = sorted((i for i in idle_items(team, now) if (i.doctype, i.name) not in listed), key=lambda i: i.since)
	return sla + idle


# --- Morning summary ------------------------------------------------------------------------------


# where the Team Cockpit opens a record (spa_shared/router.js)
COCKPIT_PATHS = {"Issue": "issues/list", "Task": "tasks/gantt"}


def _link(item):
	path = f"{get_url()}/team-cockpit/{COCKPIT_PATHS[item.doctype]}/{quote(item.name)}"
	return f'<a href="{escape_html(path)}">{escape_html(item.title or item.name)}</a>'


def summary_html(items):
	lines = [f"<li>{_link(i)}: {escape_html(i.detail)}</li>" for i in items[:SUMMARY_MAX_ITEMS]]
	if len(items) > SUMMARY_MAX_ITEMS:
		lines.append(f"<li>{escape_html(_('and {0} more in the Team Cockpit').format(len(items) - SUMMARY_MAX_ITEMS))}</li>")
	return f"<p>👀 <strong>{escape_html(_('Needs attention since the last summary'))}</strong></p><ul>{''.join(lines)}</ul>"


def _window(now):
	"""Since the last summary: a day; on Monday the weekend too (the summary runs on weekdays)."""
	return SUMMARY_WINDOW * (3 if now.weekday() == 0 else 1)


def new_items(team, now=None):
	"""Items that started to need attention since the last summary."""
	now = get_datetime(now or now_datetime())
	since = now - _window(now)
	return [i for i in attention_items(team, now) if since < i.since <= now]


def post_summary(team, now=None):
	"""One message in the team chat with the new items; nothing on a quiet day. Returns the count."""
	from phamos.cockpits.team_successes import _post_in_team_chat

	items = new_items(team, now)
	if items:
		_post_in_team_chat(team, summary_html(items))
	return len(items)


def post_all_summaries():
	"""Morning job (weekdays): one summary per team."""
	for team in frappe.get_all("Team", pluck="name"):
		try:
			post_summary(team)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Needs attention summary of {team} not posted")
