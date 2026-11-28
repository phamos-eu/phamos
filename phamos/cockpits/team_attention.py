# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit "Needs attention" (#2235): the team's open Issues and Tasks that lie around, and
Issues whose SLA was missed or is due soon. A list of records for the team as a whole, never a
figure per person (decision 3 of #1954).

Each item has a `key` for what it is about: an idle period (by its last activity) or an SLA
deadline. The morning summary posts the items whose key it has not announced yet (Team Attention
Notice), so a late, missed or repeated run neither repeats nor drops items, and "due" turning into
"missed" for the same deadline is not posted again. The first run records everything without
posting, so the chat is not flooded on day one.
"""

import json
from datetime import timedelta
from urllib.parse import quote

import frappe
from frappe import _
from frappe.utils import cint, escape_html, get_datetime, get_url, now_datetime

DEFAULT_IDLE_DAYS = 10
DEFAULT_SLA_DUE_HOURS = 24
SUMMARY_MAX_ITEMS = 15
LIST_LIMIT = 200
NOTICE = "Team Attention Notice"

DONE_STATUS = {
	# Issue statuses that are done; Task statuses that are done or not real work
	"Issue": ["Resolved", "Closed"],
	"Task": ["Completed", "Cancelled", "Template"],
}
# Issues waiting on the customer: nothing the team can do, so not "idle" (plus each SLA's pause statuses)
WAITING_ISSUE_STATUS = ["Replied", "On Hold"]
# SLA states that still run; others (Fulfilled, or an SLA that was switched off) are not signals
RUNNING_AGREEMENT = ["First Response Due", "Resolution Due", "Failed"]


def _settings():
	from phamos.cockpits.settings import COCKPIT_SETTINGS

	idle = cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "team_attention_idle_days")) or DEFAULT_IDLE_DAYS
	due = cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "team_attention_sla_due_hours")) or DEFAULT_SLA_DUE_HOURS
	return idle, due


def summary_on():
	from phamos.cockpits.settings import COCKPIT_SETTINGS

	value = frappe.db.get_single_value(COCKPIT_SETTINGS, "team_attention_summary")
	return value is None or bool(cint(value))


def sla_on():
	return bool(frappe.db.get_single_value("Support Settings", "track_service_level_agreement"))


def _waiting_statuses():
	paused = frappe.get_all("Pause SLA On Status", pluck="status", distinct=True) if frappe.db.table_exists("Pause SLA On Status") else []
	return sorted(set(WAITING_ISSUE_STATUS) | set(paused))


def _open_records(doctype, team, fields, extra_filters=(), as_user=False):
	"""The team's open records. As the user (the page): their read rights apply; the morning job
	reads all and posts only to the team's own chat."""
	from phamos.api.department_cockpit import _team_or_filters

	if as_user and not frappe.has_permission(doctype, "read"):
		return []  # e.g. no Task rights: the page shows the Issues only
	getter = frappe.get_list if as_user else frappe.get_all
	return getter(
		doctype,
		filters=[["status", "not in", DONE_STATUS[doctype]], *extra_filters],
		or_filters=_team_or_filters(team),
		fields=["name", "modified", "creation", "_assign", *fields],
		limit_page_length=0,
	)


def _latest_reference(table, doctype, names, extra=None):
	"""{name: latest creation} of the Comments or Communications on `names`."""
	if not names:
		return {}
	rows = frappe.get_all(
		table,
		filters={"reference_doctype": doctype, "reference_name": ["in", names], **(extra or {})},
		fields=["reference_name", "max(creation) as latest"],
		group_by="reference_name",
	)
	return {r.reference_name: r.latest for r in rows}


def _latest_timesheets(names):
	if not names:
		return {}
	rows = frappe.db.sql(
		"""select td.task, max(coalesce(td.to_time, td.from_time)) from `tabTimesheet Detail` td
		join `tabTimesheet` t on t.name = td.parent and t.docstatus < 2
		where td.task in %(names)s group by td.task""",
		{"names": tuple(names)},
	)
	return {task: latest for task, latest in rows}


def _last_activity(doctype, rows):
	"""{name: last change, comment, mail or timesheet}. Only real comments count, not likes or shares."""
	names = [r.name for r in rows]
	latest = {r.name: get_datetime(r.modified) for r in rows}
	sources = [
		_latest_reference("Comment", doctype, names, {"comment_type": "Comment"}),
		_latest_reference("Communication", doctype, names),
	]
	if doctype == "Task":
		sources.append(_latest_timesheets(names))
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


def _item(doctype, row, kind, key, detail, order):
	return frappe._dict(
		doctype=doctype,
		name=row.name,
		title=row.subject,
		kind=kind,
		key=f"{doctype}:{row.name}:{key}",
		detail=detail,
		order=order,
		assignees=_assignees(row._assign),
	)


def idle_items(team, now=None, as_user=False):
	"""Open Issues and Tasks of the team with no change, comment, mail or timesheet for N days.
	Issues waiting on the customer are left out."""
	now = get_datetime(now or now_datetime())
	idle_days, _due = _settings()
	limit = now - timedelta(days=idle_days)
	found = []
	for doctype in ("Issue", "Task"):
		extra = [["status", "not in", _waiting_statuses()]] if doctype == "Issue" else []
		rows = _open_records(doctype, team, ["subject"], extra, as_user)
		activity = _last_activity(doctype, rows)
		for row in rows:
			last = activity.get(row.name) or get_datetime(row.creation)
			if last <= limit:
				# keyed by the last activity: a record that moves and lies around again is news again
				found.append(
					_item(doctype, row, "idle", f"idle:{last:%Y-%m-%d %H:%M:%S}", _("No activity for {0} days").format((now - last).days), last)
				)
	return found


def sla_items(team, now=None, as_user=False):
	"""Open Issues of the team whose SLA response or resolution was missed or is due soon; only
	while SLA tracking is on (decision 2 of #1981), and only while their SLA runs.

	Deadlines are compared in system time; ERPNext computes them in the Issue owner's time zone,
	which is the system's for phamos' users."""
	if not sla_on():
		return []
	now = get_datetime(now or now_datetime())
	_idle, due_hours = _settings()
	window = timedelta(hours=due_hours)
	found = []
	rows = _open_records(
		"Issue",
		team,
		["subject", "response_by", "first_responded_on", "sla_resolution_by", "sla_resolution_date"],
		[["service_level_agreement", "is", "set"], ["agreement_status", "in", RUNNING_AGREEMENT]],
		as_user,
	)
	for row in rows:
		checks = (
			("response", row.response_by, row.first_responded_on, _("First response missed"), _("First response due")),
			("resolution", row.sla_resolution_by, row.sla_resolution_date, _("Resolution missed"), _("Resolution due")),
		)
		for part, deadline, done, missed, due in checks:
			if not deadline or done:
				continue
			deadline = get_datetime(deadline)
			if deadline <= now or deadline - window <= now:
				late = deadline <= now
				# keyed by the deadline: "due" and then "missed" for the same deadline is one notice
				found.append(
					_item("Issue", row, f"{part}_{'missed' if late else 'due'}", f"{part}:{deadline:%Y-%m-%d %H:%M:%S}", missed if late else due, deadline)
				)
				break  # the response first; the resolution once it is answered
	return found


def attention_items(team, now=None, as_user=False):
	"""SLA items first (most urgent first), then idle records (longest idle first). An Issue with an
	SLA item is not listed again as idle."""
	sla = sorted(sla_items(team, now, as_user), key=lambda i: i.order)
	listed = {(i.doctype, i.name) for i in sla}
	idle = sorted((i for i in idle_items(team, now, as_user) if (i.doctype, i.name) not in listed), key=lambda i: i.order)
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


def _notice_key(team, item):
	return f"{team}|{item.key}"[:140]


def new_items(team, now=None):
	"""Items the team's summary has not announced yet."""
	items = attention_items(team, now)
	keys = [_notice_key(team, i) for i in items]
	known = set(frappe.get_all(NOTICE, filters={"dedupe_key": ["in", keys]}, pluck="dedupe_key")) if keys else set()
	return [i for i in items if _notice_key(team, i) not in known]


def post_summary(team, now=None):
	"""One message in the team chat with the new items; nothing on a quiet day, nothing on the
	team's first run (all is recorded silently). Returns the number posted."""
	from phamos.cockpits.team_successes import _post_in_team_chat

	now = get_datetime(now or now_datetime())
	first_run = not frappe.db.exists(NOTICE, {"team": team})
	items = new_items(team, now)
	for item in items:
		frappe.get_doc(
			{
				"doctype": NOTICE,
				"team": team,
				"dedupe_key": _notice_key(team, item),
				"reference_doctype": item.doctype,
				"reference_name": item.name,
				"posted_on": None if first_run else now,
			}
		).insert(ignore_permissions=True)
	if not items or first_run:
		return 0
	_post_in_team_chat(team, summary_html(items))
	return len(items)


def post_all_summaries():
	"""Morning job (weekdays 07:30): one summary per team, when switched on in Cockpit Settings."""
	if not summary_on():
		return
	for team in frappe.get_all("Team", pluck="name"):
		try:
			post_summary(team)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Needs attention summary of {team} not posted")
