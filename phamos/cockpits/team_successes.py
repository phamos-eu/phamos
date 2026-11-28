# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team successes (#1981): small daily rules, kudos and customer praise.

Every rule is a function `rule(ctx)` that returns candidate successes. Each candidate carries a
`key` unique per team, rule and period or record; the daily job writes only keys it has not seen,
so running it twice writes nothing new. Rules that react to an event (a parent item closed, a
maturity level raised, a module at target, an idea harvested, an Issue picked up) look only at the
last RECENT_DAYS days: the first run must not flood the team with everything ever achieved.
Record and month rules look at the last full month and are keyed by it.

A new success is posted in the team chat (#1978) when the team has one. Nothing here is a figure
per person: a success may name the person it is about, never rank people (decision 3 of #1954).
"""

from datetime import timedelta
from statistics import median

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, escape_html, get_first_day, get_last_day, getdate, today

from phamos.cockpits import teams

RECENT_DAYS = 7
STREAK_MIN_WEEKS = 4
STREAK_MAX_WEEKS = 12
BOOKED_TARGET = 95  # % of available hours
PREDICTION_TOLERANCE = 0.10
OLD_ITEM_DAYS = 90
DEFAULT_PICKED_UP_IDLE_DAYS = 14
MATURITY_FIELD = "maturity_level"
FORECAST_FIELD = "forecast"

RULES = []


def rule(fn):
	RULES.append(fn)
	return fn


def _level(value):
	"""'3 - Development Phase…' -> 3; '2 🌤️ - …' -> 2; else None."""
	try:
		return int(str(value or "").strip().split(" ")[0])
	except ValueError:
		return None


def _month_key(day):
	return getdate(day).strftime("%Y-%m")


def _last_full_month(day):
	first = get_first_day(add_months(day, -1))
	return first, getdate(get_last_day(first))


class Context:
	"""What the rules of one team share, computed once per run."""

	def __init__(self, team, day):
		from phamos.cockpits import team_gitlab

		self.team = team
		self.today = getdate(day)
		self.recent_from = add_days(self.today, -RECENT_DAYS)
		self.implementations = frappe.get_all("Implementation", filters={"team": team}, pluck="name")
		self.projects = teams.team_projects(team)
		self._gitlab = None
		self._team_gitlab = team_gitlab

	@property
	def gitlab(self):
		if self._gitlab is None:
			self._gitlab = self._team_gitlab.team_gitlab_statistics(self.team, today=self.today)
		return self._gitlab

	def member(self, user):
		"""The Employee of `user` if they are in the team today."""
		employee = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")
		return employee if employee and user in {row["name"] for row in teams.team_users(self.team)} else None


def _success(key, success_type, title, text="", employee=None, reference=None):
	return frappe._dict(
		key=key,
		success_type=success_type,
		title=title,
		text=text,
		employee=employee,
		reference_doctype=reference[0] if reference else None,
		reference_name=reference[1] if reference else None,
	)


# --- Delivery (GitLab) ---------------------------------------------------------------------------


@rule
def parent_item_shipped(ctx):
	"""A parent item of the team's own implementations closed in the last days, all children closed."""
	from phamos.cockpits.team_gitlab import _project_groups

	_groups, own = _project_groups(ctx.team)
	if not own:
		return []
	found = []
	for parent in frappe.get_all(
		"GitLab Issue",
		filters={"gitlab_project": ["in", list(own)], "state": "closed", "closed_at": [">=", ctx.recent_from]},
		fields=["name", "title"],
	):
		children = frappe.get_all("GitLab Issue", filters={"parent_issue": parent.name}, pluck="state")
		if children and all(state == "closed" for state in children):
			found.append(
				_success(
					f"parent:{parent.name}",
					"Delivery",
					_("Shipped: {0}").format(parent.title),
					_("The parent item and all {0} of its items are closed.").format(len(children)),
					reference=("GitLab Issue", parent.name),
				)
			)
	return found


@rule
def milestone_on_time(ctx):
	"""A milestone of the team's own implementations closed, not after its due date."""
	from phamos.cockpits.team_gitlab import _project_groups

	_groups, own = _project_groups(ctx.team)
	if not own:
		return []
	return [
		_success(
			f"milestone:{m.name}",
			"Delivery",
			_("Milestone on time: {0}").format(m.title),
			reference=("GitLab Milestones", m.name),
		)
		for m in frappe.get_all(
			"GitLab Milestones",
			filters={"gitlab_project": ["in", list(own)], "state": "closed", "modified": [">=", ctx.recent_from]},
			fields=["name", "title", "due_date", "modified"],
		)
		if m.due_date and getdate(m.modified) <= getdate(m.due_date)
	]


@rule
def record_month(ctx):
	"""The last full month had the most closed items, or the shortest median closing time, of the year."""
	months = ctx.gitlab.months[:-1]  # the current month is still running
	if len(months) < 3:
		return []
	last, earlier = months[-1], months[:-1]
	key_month = _month_key(last.start)
	found = []
	if last.closed_total and last.closed_total > max(m.closed_total or 0 for m in earlier):
		found.append(
			_success(
				f"record_closed:{key_month}",
				"Delivery",
				_("Record month: {0} items closed").format(last.closed_total),
				_("More than in any of the {0} months before.").format(len(earlier)),
			)
		)
	medians = [m.work_item_median for m in earlier if m.work_item_median is not None]
	if last.work_item_median is not None and medians and last.closed_total >= 3 and last.work_item_median < min(medians):
		found.append(
			_success(
				f"record_speed:{key_month}",
				"Delivery",
				_("Fastest month: items closed in {0} days (median)").format(last.work_item_median),
			)
		)
	return found


@rule
def no_old_open_items(ctx):
	"""No open item of the team older than OLD_ITEM_DAYS days (once a month)."""
	open_items = ctx.gitlab.open_items
	if not open_items.count or (open_items.oldest_age_days or 0) >= OLD_ITEM_DAYS:
		return []
	return [
		_success(
			f"no_old_items:{_month_key(ctx.today)}",
			"Delivery",
			_("No open item older than {0} days").format(OLD_ITEM_DAYS),
			_("{0} items open, the oldest {1} days.").format(open_items.count, open_items.oldest_age_days),
		)
	]


# --- Implementations -----------------------------------------------------------------------------


def _changes(doctype, names, field, since):
	"""(version name, doc name, old, new, owner) of changes to `field` since `since`."""
	if not names:
		return []
	rows = []
	for version in frappe.get_all(
		"Version",
		filters={"ref_doctype": doctype, "docname": ["in", names], "creation": [">=", since]},
		fields=["name", "docname", "data", "owner"],
		order_by="creation asc",
	):
		data = frappe.parse_json(version.data or "{}")
		for change in data.get("changed") or []:
			if change and change[0] == field:
				rows.append((version.name, version.docname, change[1], change[2], version.owner))
	return rows


@rule
def implementation_steps(ctx):
	"""A maturity level raised or a forecast improved in the last days."""
	found = []
	for version, implementation, old, new, _owner in _changes("Implementation", ctx.implementations, MATURITY_FIELD, ctx.recent_from):
		if _level(old) is not None and _level(new) is not None and _level(new) > _level(old):
			found.append(
				_success(
					f"maturity:{version}",
					"Implementations",
					_("{0} reached maturity level {1}").format(implementation, _level(new)),
					reference=("Implementation", implementation),
				)
			)
	for version, implementation, old, new, _owner in _changes("Implementation", ctx.implementations, FORECAST_FIELD, ctx.recent_from):
		# 1 ☀️ is the best forecast
		if _level(old) is not None and _level(new) is not None and _level(new) < _level(old):
			found.append(
				_success(
					f"forecast:{version}",
					"Implementations",
					_("{0}: the forecast improved").format(implementation),
					reference=("Implementation", implementation),
				)
			)
	return found


@rule
def module_at_target(ctx):
	"""A module of the team's implementations reached its target level in the last days."""
	if not ctx.implementations:
		return []
	return [
		_success(
			f"module:{row.name}:{row.target_level}",
			"Implementations",
			_("{0}: {1} reached level {2}").format(row.parent, row.module, row.target_level),
			reference=("Implementation", row.parent),
		)
		for row in frappe.get_all(
			"Implementation Item",
			filters={"parenttype": "Implementation", "parent": ["in", ctx.implementations], "modified": [">=", ctx.recent_from]},
			fields=["name", "parent", "module", "current_level", "target_level"],
		)
		if cint(row.target_level) and cint(row.current_level) >= cint(row.target_level)
	]


def _implementation_hours(implementation, start, end):
	return frappe.db.sql(
		"""
		select ifnull(sum(td.hours), 0)
		from `tabTimesheet Detail` td
		join `tabTimesheet` t on t.name = td.parent and t.docstatus < 2
		join `tabProject` p on p.name = td.project
		where p.custom_implementation = %(implementation)s
			and td.from_time >= %(start)s and td.from_time < %(after_end)s
		""",
		{"implementation": implementation, "start": start, "after_end": add_days(end, 1)},
	)[0][0]


@rule
def implementation_hours(ctx):
	"""A monthly hours budget kept three months in a row; actual hours within 10 % of the prediction."""
	if not ctx.implementations or not frappe.db.has_column("Project", "custom_implementation"):
		return []
	found = []
	start, end = _last_full_month(ctx.today)
	key_month = _month_key(start)
	for impl in frappe.get_all(
		"Implementation",
		filters={"name": ["in", ctx.implementations]},
		fields=["name", "enable_time_limit", "recurring_monthly", "limit_hours"],
	):
		if impl.enable_time_limit and impl.recurring_monthly and impl.limit_hours:
			months = [get_first_day(add_months(start, -i)) for i in range(3)]
			if all(
				_implementation_hours(impl.name, m, getdate(get_last_day(m))) <= impl.limit_hours for m in months
			):
				found.append(
					_success(
						f"budget:{impl.name}:{key_month}",
						"Implementations",
						_("{0}: hours budget kept three months in a row").format(impl.name),
						reference=("Implementation", impl.name),
					)
				)
		predicted = frappe.db.get_value(
			"Prediction",
			{"parent": impl.name, "parenttype": "Implementation", "month_and_year": start.strftime("%B %Y")},
			"prediction",
		)
		if predicted:
			actual = _implementation_hours(impl.name, start, end)
			if actual and abs(actual - predicted) <= PREDICTION_TOLERANCE * predicted:
				found.append(
					_success(
						f"prediction:{impl.name}:{key_month}",
						"Implementations",
						_("{0}: {1} h, within 10 % of the {2} h predicted").format(impl.name, round(actual), predicted),
						reference=("Implementation", impl.name),
					)
				)
	return found


# --- Timesheets ----------------------------------------------------------------------------------


def _booked_rows(team, start, end):
	"""Member rows (team_hours.member_row) of the team for [start, end]."""
	from phamos.cockpits import team_hours
	from phamos.phamos.doctype.team_assignment.team_assignment import members_between

	rows = []
	for employee, periods in members_between(team, start, end).items():
		days = team_hours.member_days(employee, periods)
		row = team_hours.member_row(employee, employee, days, start, end)
		if row:
			rows.append(row)
	return rows


@rule
def complete_timesheets(ctx):
	"""Every member with working hours booked at least 95 % of them last month; and a streak of
	complete weeks (the team booked 95 % or more, at least four weeks in a row)."""
	from phamos.cockpits import team_hours

	found = []
	start, end = _last_full_month(ctx.today)
	rows = [r for r in _booked_rows(ctx.team, start, end) if r.known and r.available_known]
	if rows and all((r.booked_rate or 0) >= BOOKED_TARGET for r in rows):
		found.append(
			_success(
				f"timesheets_month:{_month_key(start)}",
				"Timesheets",
				_("Everyone booked their hours in {0}").format(start.strftime("%B %Y")),
				_("Each of the {0} members with working hours booked at least {1} %.").format(len(rows), BOOKED_TARGET),
			)
		)
	week_start = ctx.today - timedelta(days=ctx.today.weekday() + 7)  # Monday of last week
	streak = 0
	for i in range(STREAK_MAX_WEEKS):
		w_start = week_start - timedelta(weeks=i)
		totals = team_hours.totals(_booked_rows(ctx.team, w_start, w_start + timedelta(days=6)), 7)
		if (totals.booked_rate or 0) < BOOKED_TARGET:
			break
		streak += 1
	if streak >= STREAK_MIN_WEEKS:
		found.append(
			_success(
				f"timesheets_streak:{week_start}",
				"Timesheets",
				_("{0} complete weeks in a row").format(streak),
				_("The team booked at least {0} % of its available hours every week.").format(BOOKED_TARGET),
			)
		)
	return found


# --- Team ideas ----------------------------------------------------------------------------------


@rule
def idea_harvested(ctx):
	"""An idea shared with the team reached the Harvest stage in the last days."""
	return [
		_success(
			f"idea:{idea.name}",
			"Team ideas",
			_("Idea harvested: {0}").format(idea.title),
			reference=("Idea", idea.name),
		)
		for idea in frappe.get_all(
			"Idea",
			filters={"team": ctx.team, "stage": "Harvest", "harvested_on": [">=", ctx.recent_from]},
			fields=["name", "title"],
		)
	]


# --- Picked up -----------------------------------------------------------------------------------


@rule
def picked_up(ctx):
	"""An Issue without a team, idle for N days (Cockpit Settings), that the team took on in the last
	days: its Team field went from empty to this team."""
	from phamos.cockpits.settings import COCKPIT_SETTINGS

	idle_days = cint(frappe.db.get_single_value(COCKPIT_SETTINGS, "team_picked_up_idle_days")) or DEFAULT_PICKED_UP_IDLE_DAYS
	found = []
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": "Issue", "creation": [">=", ctx.recent_from], "data": ["like", '%"custom_team"%']},
		fields=["name", "docname", "data", "owner", "creation"],
		order_by="creation asc",
	)
	for version in versions:
		data = frappe.parse_json(version.data or "{}")
		change = next((c for c in data.get("changed") or [] if c and c[0] == "custom_team"), None)
		if not change or change[1] or change[2] != ctx.team:
			continue
		issue = frappe.db.get_value("Issue", version.docname, ["subject", "project", "creation"], as_dict=True)
		if not issue or (issue.project and issue.project in ctx.projects):
			continue  # it belonged to the team through its project already
		previous = frappe.get_all(
			"Version",
			filters={"ref_doctype": "Issue", "docname": version.docname, "creation": ["<", version.creation]},
			fields=["creation"],
			order_by="creation desc",
			limit=1,
		)
		last_activity = previous[0].creation if previous else issue.creation
		if (getdate(version.creation) - getdate(last_activity)).days < idle_days:
			continue
		found.append(
			_success(
				f"picked_up:{version.docname}",
				"Picked up",
				_("Picked up: {0}").format(issue.subject),
				_("Idle for {0} days before the team took it on.").format((getdate(version.creation) - getdate(last_activity)).days),
				employee=ctx.member(version.owner),
				reference=("Issue", version.docname),
			)
		)
	return found


# --- SLA (only while SLA tracking is on) ----------------------------------------------------------


@rule
def sla_successes(ctx):
	"""Quick response (first response within its SLA time) and resolved in time (Fulfilled), in the
	last days; only while SLA tracking is on (decision 2)."""
	if not frappe.db.get_single_value("Support Settings", "track_service_level_agreement"):
		return []
	or_filters = [["custom_team", "=", ctx.team]]
	if ctx.projects:
		or_filters.append(["project", "in", ctx.projects])
	found = []
	for issue in frappe.get_all(
		"Issue",
		filters={"first_responded_on": [">=", ctx.recent_from], "response_by": ["is", "set"]},
		or_filters=or_filters,
		fields=["name", "subject", "first_responded_on", "response_by"],
	):
		if issue.first_responded_on <= issue.response_by:
			found.append(_success(f"sla_response:{issue.name}", "SLA", _("Quick response: {0}").format(issue.subject), reference=("Issue", issue.name)))
	for issue in frappe.get_all(
		"Issue",
		filters={"agreement_status": "Fulfilled", "status": ["in", ["Resolved", "Closed"]], "modified": [">=", ctx.recent_from]},
		or_filters=or_filters,
		fields=["name", "subject"],
	):
		found.append(_success(f"sla_resolved:{issue.name}", "SLA", _("Resolved in time: {0}").format(issue.subject), reference=("Issue", issue.name)))
	return found


# --- Running and writing --------------------------------------------------------------------------


def _key(team, candidate_key):
	return f"{team}|{candidate_key}"[:255]


def _post_in_team_chat(team, html):
	"""Post in the team's chat if it has one (#1978); never create a chat for it."""
	from phamos.api import issue_chat

	if not issue_chat.is_raven_installed() or not issue_chat.is_enabled():
		return
	channel = issue_chat.find_channel(issue_chat.TEAM_CHAT, team)
	if not channel or channel.is_archived:
		return
	frappe.get_doc({"doctype": "Raven Message", "channel_id": channel.name, "message_type": "Text", "text": html}).insert(
		ignore_permissions=True
	)


def record_success(team, success, given_by=None, customer=None, day=None, post=True):
	"""Write one success unless its key exists; post it in the team chat. Returns the name or None."""
	key = _key(team, success.key)
	if frappe.db.exists("Team Success", {"dedupe_key": key}):
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Team Success",
			"team": team,
			"success_type": success.success_type,
			"title": success.title[:255],
			"text": success.text,
			"date": day or today(),
			"employee": success.employee,
			"given_by": given_by,
			"customer": customer,
			"source": success.get("source") or success.key.split(":")[0],
			"dedupe_key": key,
			"reference_doctype": success.reference_doctype,
			"reference_name": success.reference_name,
		}
	)
	doc.flags.ignore_links = True
	doc.insert(ignore_permissions=True)
	if post:
		try:
			line = f"🎉 <strong>{escape_html(doc.title)}</strong>"
			if doc.text:
				line += f"<br>{escape_html(doc.text)}"
			_post_in_team_chat(team, f"<p>{line}</p>")
		except Exception:
			frappe.log_error(title=f"Team success not posted in the chat of {team}")
	return doc.name


def run_rules(team, day=None):
	"""Run every rule for one team; returns the names of the new successes. A failing rule is logged
	and skipped, the others still run."""
	ctx = Context(team, day or today())
	created = []
	for fn in RULES:
		try:
			candidates = fn(ctx) or []
		except Exception:
			frappe.log_error(title=f"Team success rule {fn.__name__} failed for {team}")
			continue
		for candidate in candidates:
			candidate.source = fn.__name__
			name = record_success(team, candidate, day=ctx.today)
			if name:
				created.append(name)
	return created


def run_all_teams():
	"""Daily job."""
	for team in frappe.get_all("Team", pluck="name"):
		try:
			run_rules(team)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"Team successes of {team} not written")


# --- Manual successes ------------------------------------------------------------------------------


def give_kudos(team, employee, text):
	"""Kudos from the session user to a team mate; the giver is visible to the team (decision 3)."""
	giver = frappe.session.user
	if employee not in _team_employees(team):
		frappe.throw(_("Kudos go to someone in team {0}.").format(team))
	if frappe.db.get_value("Employee", employee, "user_id") == giver:
		frappe.throw(_("Kudos go to someone else."))
	text = (text or "").strip()
	if not text:
		frappe.throw(_("Say what the kudos are for."))
	name = frappe.db.get_value("Employee", employee, "employee_name")
	success = _success(
		f"kudos:{frappe.generate_hash(length=10)}",
		"Kudos",
		_("{0} → {1}").format(frappe.utils.get_fullname(giver), name),
		text,
		employee=employee,
	)
	success.source = "Kudos"
	return record_success(team, success, given_by=giver)


def add_customer_praise(team, customer, text, employee=None):
	"""Praise from a customer, entered by a team member (who entered it shows)."""
	text = (text or "").strip()
	if not customer or not frappe.db.exists("Customer", customer):
		frappe.throw(_("Pick the customer who praised."))
	if not text:
		frappe.throw(_("What did the customer say?"))
	if employee and employee not in _team_employees(team):
		frappe.throw(_("The praise goes to someone in team {0}.").format(team))
	success = _success(
		f"praise:{frappe.generate_hash(length=10)}",
		"Customer praise",
		_("Praise from {0}").format(frappe.db.get_value("Customer", customer, "customer_name") or customer),
		text,
		employee=employee,
	)
	success.source = "Customer praise"
	return record_success(team, success, given_by=frappe.session.user, customer=customer)


def _team_employees(team):
	from phamos.cockpits.team_status import _people

	return set(_people(team, getdate()))


def list_successes(team, success_type=None, limit=200):
	filters = {"team": team}
	if success_type:
		filters["success_type"] = success_type
	return frappe.get_all(
		"Team Success",
		filters=filters,
		fields=[
			"name", "success_type", "title", "text", "date", "employee", "employee_name",
			"given_by", "customer", "reference_doctype", "reference_name", "creation",
		],
		order_by="date desc, creation desc",
		limit_page_length=limit,
	)
