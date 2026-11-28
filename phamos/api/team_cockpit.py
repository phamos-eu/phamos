# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit API: Issues, Tasks and Checklists of the session user's active Team (#1955).

The team is not an argument: phamos.cockpits.teams resolves it per request from the user's
membership, so the shared cockpit views work unchanged. Every whitelisted function first checks
that the user has a team at all.
"""

import functools

import frappe
from frappe import _

from phamos.api import department_cockpit as dc
from phamos.cockpits import teams

CONFIG = dc.CockpitConfig(
	label="Team",
	department_field="",
	project_field="",
	roles=(),
	settings_method_name="get_team_settings",
	scope="team",
)


def check_app_permission():
	"""True for users who may open at least one team (Apps screen, page, API)."""
	return dc.check_app_permission(CONFIG)


def _require_access(fn):
	"""Refuse a whitelisted call unless check_app_permission() passes.

	functools.wraps keeps the signature, which frappe uses to pick the request arguments.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if not check_app_permission():
			frappe.throw(_("You do not have permission to access the Team Cockpit"), frappe.PermissionError)
		return fn(*args, **kwargs)

	# Marker for the tests; functools.wraps carries it up through frappe.whitelist's own wrapper.
	wrapper.requires_team = True
	return wrapper


def _team_rows(names):
	return [{"name": name} for name in names]


@frappe.whitelist()
@_require_access
def get_teams():
	"""The teams the session user may open, and the one the cockpit shows now.

	Returns:
		dict: teams ([{name}], sorted by name) and active (a team name).
	"""
	return {"teams": _team_rows(teams.available_teams()), "active": teams.active_team()}


@frappe.whitelist(methods=["POST"])
@_require_access
def set_active_team(team):
	"""Show `team` in the session user's Team Cockpit from now on. Only a team they may open."""
	teams.set_active_team(team)
	return get_teams()


@frappe.whitelist()
@_require_access
def get_team_settings():
	"""Return the Team Cockpit configuration for the frontend.

	Requires read permission on Issue (checked in department_cockpit.get_settings).

	Returns:
		dict: team (the active team's name) and teams (every team the user may open).
	"""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
@_require_access
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the team timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
@_require_access
def get_inbox(view="assigned", include_closed=0):
	"""Return team-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issues(include_closed=0):
	"""Return all team Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issue(name):
	"""Return Issue detail if it belongs to team scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_form_options():
	"""Form options scoped to team."""
	return dc.get_form_options(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create a team-scoped Issue."""
	return dc.create_issue(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_status(name, status):
	"""Update Issue status within team scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_assignees(name, users=None):
	"""Replace Issue assignees within team scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist()
@_require_access
def get_issue_chat(name):
	"""Return the Raven chat state of an Issue in team scope."""
	return dc.get_issue_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_issue_chat(name):
	"""Start or join the Raven chat of an Issue in team scope."""
	return dc.ensure_issue_chat(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_issue_chat_states(names):
	"""Return the chat state per Issue for list views."""
	return dc.get_issue_chat_states(names)


@frappe.whitelist()
@_require_access
def get_task_chat(name):
	"""Return the Raven chat state of a Task in team scope."""
	return dc.get_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_task_chat(name):
	"""Start or join the Raven chat of a Task in team scope."""
	return dc.ensure_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_issue(
	name,
	subject=None,
	description=None,
	priority=None,
	issue_type=None,
	project=None,
	custom_team=None,
	modified=None,
):
	"""Update whitelisted Issue fields within team scope."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if issue_type is not None:
		fields["issue_type"] = issue_type
	if project is not None:
		fields["project"] = project
	if custom_team is not None:
		fields["custom_team"] = custom_team
	if modified is not None:
		fields["modified"] = modified
	return dc.update_issue(CONFIG, name, **fields)


@frappe.whitelist()
@_require_access
def get_tasks(include_completed=0):
	"""Return Tasks for the team."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklists(include_completed=0):
	"""Return Checklists linked to team Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklist_dashboard():
	"""Return team Checklist dashboard metrics and chart data."""
	return dc.get_checklist_dashboard(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_checklist(
	document,
	reference_record,
	name=None,
	items=None,
	checklist_owner=None,
	checklist_template=None,
):
	"""Create a Checklist linked to a team Issue or Task."""
	return dc.create_checklist(
		CONFIG,
		document,
		reference_record,
		name=name,
		items=items,
		checklist_owner=checklist_owner,
		checklist_template=checklist_template,
	)


# _require_access goes outside the search decorator: that one maps the positional arguments the
# link search passes by the function's own argument names, which a wrapper below it would hide.
@frappe.whitelist()
@_require_access
@frappe.validate_and_sanitize_search_inputs
def checklist_reference_query(doctype, txt, searchfield, start, page_len, filters):
	"""Search team-scoped Issue/Task parents for Checklist creation."""
	return dc.checklist_reference_query(CONFIG, doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
@_require_access
def get_task(name):
	"""Return Task detail for the team SPA."""
	return dc.get_task(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	return dc.update_task_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	return dc.update_task_dates(CONFIG, name, exp_start_date=exp_start_date, exp_end_date=exp_end_date)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task(
	name,
	subject=None,
	description=None,
	priority=None,
	status=None,
	exp_start_date=None,
	exp_end_date=None,
	progress=None,
	project=None,
	custom_task_owner=None,
	custom_team=None,
	modified=None,
):
	"""Update whitelisted Task fields within team scope."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if status is not None:
		fields["status"] = status
	if exp_start_date is not None:
		fields["exp_start_date"] = exp_start_date
	if exp_end_date is not None:
		fields["exp_end_date"] = exp_end_date
	if progress is not None:
		fields["progress"] = progress
	if project is not None:
		fields["project"] = project
	if custom_task_owner is not None:
		fields["custom_task_owner"] = custom_task_owner
	if custom_team is not None:
		fields["custom_team"] = custom_team
	if modified is not None:
		fields["modified"] = modified
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_task_assignees(name, users=None):
	"""Replace Task assignees within team scope."""
	return dc.set_task_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
	expected_time=None,
	custom_task_owner=None,
	task_type=None,
):
	"""Create a Task in the team."""
	return dc.create_task(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		project=project,
		department=department,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		expected_time=expected_time,
		custom_task_owner=custom_task_owner,
		task_type=task_type,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_task_from_issue(
	issue_name,
	exp_start_date,
	exp_end_date,
	assignees=None,
	subject=None,
	description=None,
	priority=None,
	project=None,
	depends_on=None,
):
	"""Convert an Issue into a Task (Team Cockpit hand-off)."""
	return dc.create_task_from_issue(
		CONFIG,
		issue_name,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		assignees=assignees,
		subject=subject,
		description=description,
		priority=priority,
		project=project,
		depends_on=depends_on,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)


@frappe.whitelist(methods=["POST"])
@_require_access
def remove_task_dependency(name, depends_on):
	"""Remove a predecessor from a Task (side panel, Gantt)."""
	return dc.remove_task_dependency(CONFIG, name, depends_on)


@frappe.whitelist()
@_require_access
def search_dependency_candidates(name, txt=""):
	"""Tasks the given Task could depend on, for the side panel's search."""
	return dc.search_dependency_candidates(CONFIG, name, txt)


# --- Statistics and Implementations (#1975): hours only, no currency -------------------------

MEMBER_HOURS_SETTING = "show_member_hours_to_team_leads"


def _leads_team(team, employee):
	lead, co_lead = frappe.db.get_value("Team", team, ["team_lead", "co_team_lead"]) or (None, None)
	return bool(employee) and employee in (lead, co_lead)


def _sees_member_rows(team, employee):
	"""Per-person rows of others: lead or co-lead of the team (General Management and System Manager
	too), and only while "Show member hours to team leads" is on in phamos Settings. The setting is
	off until phamos' privacy owner has confirmed the legal side (decision 5 of #1975)."""
	if not frappe.db.get_single_value("phamos Settings", MEMBER_HOURS_SETTING):
		return False
	return teams.sees_all_teams() or _leads_team(team, employee)


def _sees_missing_hours(team, employee):
	"""Data-quality notices (missing working hours, unmatched GitLab items) are for lead, co-lead and HR."""
	return teams.sees_all_teams() or "HR Manager" in frappe.get_roles() or _leads_team(team, employee)


@frappe.whitelist()
@_require_access
def get_hours_statistics():
	"""Logged against available hours of the active team: this month to date compared with the
	previous month and last year, 12 months, year to date. Member rows: the user's own, or every
	member's for those allowed (_sees_member_rows)."""
	from phamos.cockpits import team_hours

	team = teams.require_active_team()
	employee = teams._employee(frappe.session.user)
	data = team_hours.team_statistics(team)
	sees_members = _sees_member_rows(team, employee)
	for window in data.windows.values():
		window.members = [r for r in window.members if sees_members or r.employee == employee]
	if not _sees_missing_hours(team, employee):
		data.missing_hours = []
	data.team = team
	data.sees_members = sees_members
	return data


IMPLEMENTATION_FIELDS = [
	"name",
	"customer",
	"status",
	"maturity_level",
	"forecast",
	"trend",
	"enable_time_limit",
	"limit_hours",
	"hours_used_this_period",
	"time_limit_percent_used",
	"time_limit_from_date",
	"time_limit_to_date",
	"sales_order_total_hrs",
	"delivered_total_hrs",
	"remaining_hrs",
	"total_time_last_3_months",
	"predicted_time_next_3_months",
]


@frappe.whitelist()
@_require_access
def get_team_implementations():
	"""The active team's open Implementations, hours only: time limit, sold against delivered,
	actual hours of the last 6 months against the prediction, maturity, forecast, trend, module
	levels. Fields are listed explicitly so no currency field leaves the server."""
	from frappe.utils import add_months, get_first_day, getdate, today

	team = teams.require_active_team()
	rows = frappe.get_all(
		"Implementation",
		filters={"team": team, "status": ["not in", ["Cancelled", "Completed"]]},
		fields=IMPLEMENTATION_FIELDS,
		order_by="name asc",
		limit_page_length=0,
	)
	if not rows:
		return {"team": team, "implementations": [], "can_open": False}

	names = [r.name for r in rows]
	modules = frappe.get_all(
		"Implementation Item",
		filters={"parenttype": "Implementation", "parent": ["in", names]},
		fields=["parent", "module", "current_level", "target_level"],
		order_by="idx asc",
		limit_page_length=0,
	)
	start = get_first_day(add_months(today(), -5))
	monthly = {}
	if frappe.db.has_column("Project", "custom_implementation"):
		for row in frappe.db.sql(
			"""
			select p.custom_implementation as implementation,
				date_format(td.from_time, '%%Y-%%m') as month, sum(td.hours) as hours
			from `tabTimesheet Detail` td
			join `tabTimesheet` t on t.name = td.parent and t.docstatus < 2
			join `tabProject` p on p.name = td.project
			where p.custom_implementation in %(names)s and date(td.from_time) >= %(start)s
			group by 1, 2
			""",
			{"names": names, "start": start},
			as_dict=True,
		):
			monthly[(row.implementation, row.month)] = round(row.hours or 0, 1)

	months = [getdate(add_months(start, i)) for i in range(6)]
	for row in rows:
		row.modules = [m for m in modules if m.parent == row.name]
		for m in row.modules:
			m.pop("parent")
		# ISO month start; the page formats it in the user's language
		row.months = [{"start": m, "hours": monthly.get((row.name, m.strftime("%Y-%m")), 0)} for m in months]
		# predicted_time_next_3_months is a 3-month total: a monthly figure to compare with
		row.predicted_per_month = round((row.predicted_time_next_3_months or 0) / 3, 1)
	# Team members see their team's implementations here (#1975), but only those who may read
	# Implementation get the link to its Desk form.
	return {"team": team, "implementations": rows, "can_open": bool(frappe.has_permission("Implementation", "read"))}


@frappe.whitelist()
@_require_access
def get_gitlab_statistics():
	"""GitLab figures of the active team's people and the SLA figures of its Issues (#1976). Team
	totals only, no figures per person. The count of unmatched items in the team's own projects is a
	data-quality notice for lead, co-lead and HR, like the missing working hours."""
	from phamos.cockpits import team_gitlab

	team = teams.require_active_team()
	employee = teams._employee(frappe.session.user)
	data = team_gitlab.team_gitlab_statistics(team)
	if not _sees_missing_hours(team, employee):
		data.unmatched_own_items = None
	data.team = team
	return data


# --- Team mates and team chat (#1978) -------------------------------------------------------


@frappe.whitelist()
@_require_access
def get_team_mates():
	"""The active team's people with their status today. Every team member sees every row:
	presence, focus, and project and task of a running timer (decision 1 of #1978)."""
	from phamos.cockpits import team_status

	team = teams.require_active_team()
	return {"team": team, "members": team_status.team_mates(team), "event": team_status.EVENT}


def _team_doc(name):
	"""The Team, if the session user may open it (its people, General Management, System Manager)."""
	if not name or name not in teams.available_teams():
		frappe.throw(_("You are not a member of team {0}.").format(name or ""), frappe.PermissionError)
	return frappe.get_doc("Team", name)


@frappe.whitelist()
@_require_access
def get_team_chat(name):
	"""Chat state of the team's Raven channel (IssueChatButton calls get_<doctype>_chat)."""
	from phamos.api import issue_chat

	return issue_chat.get_chat(_team_doc(name))


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_team_chat(name):
	"""Create or join the team's chat; its members are the team's people (#1978)."""
	from phamos.api import issue_chat

	return issue_chat.ensure_chat(_team_doc(name))


# --- Appointments with leave and public holidays (#1979) ------------------------------------


def _active_team_doc():
	return frappe.get_doc("Team", teams.require_active_team())


def _team_emails(team):
	"""Invite addresses of the team's people today: company email, else their user."""
	from phamos.cockpits.team_status import _people

	emails = []
	for row in frappe.get_all(
		"Employee",
		filters={"name": ["in", _people(team, frappe.utils.getdate()) or [""]], "status": "Active"},
		fields=["company_email", "user_id"],
		order_by="employee_name asc",
	):
		email = row.company_email or row.user_id
		if email and email not in emails:
			emails.append(email)
	return emails


@frappe.whitelist()
@_require_access
def get_team_appointments():
	"""The active team's appointments (its Event Schedule rows), and the default attendees of a
	new one: every person of the team (decision 1 of #1979)."""
	from phamos.cockpits import appointments

	doc = _active_team_doc()
	return {
		"team": doc.name,
		"appointments": appointments.list_appointments(doc),
		"default_attendees": _team_emails(doc.name),
		"has_mailbox": bool(_team_mailboxes(doc)),
	}


def _team_mailboxes(team_doc):
	"""Team invites go out only from the Team's shared mailbox (decision 4 of #1979): members must
	not send as a colleague or a manager."""
	from phamos.cockpits import appointments

	return appointments.mailbox(team_doc.get("team_mailbox"))


@frappe.whitelist()
@_require_access
def get_appointment_options():
	"""What the appointment dialog offers: the team's mailbox and the people by department."""
	from phamos.cockpits import appointments

	return appointments.appointment_options(mailboxes=_team_mailboxes(_active_team_doc()))


@frappe.whitelist(methods=["POST"])
@_require_access
def save_appointment(appointment):
	"""Create or update an appointment of the active team and send its invite. Every member may
	plan (decision 9 of #1954)."""
	from phamos.cockpits import appointments

	doc = _active_team_doc()
	mailboxes = _team_mailboxes(doc)
	if not mailboxes:
		frappe.throw(_("Set a team mailbox with a Mailcow calendar on team {0} first.").format(doc.name))
	return appointments.save_appointment(doc, appointment, mailboxes=mailboxes)


@frappe.whitelist(methods=["POST"])
@_require_access
def delete_appointment(name):
	"""Remove an appointment of the active team; the Mailcow sync cancels its invite."""
	from phamos.cockpits import appointments

	return appointments.delete_appointment(_active_team_doc(), name)


@frappe.whitelist()
@_require_access
def get_team_absences(start, end):
	"""The calendar's read-only layer for [start, end] (decision 2 of #1979): approved leave of the
	team's people as a neutral "absent" (no leave type), and public holidays (no weekly offs) with
	the people they apply to."""
	from phamos.cockpits.team_status import _people
	from phamos.phamos.team_capacity_utils import employee_holiday_list

	start, end = frappe.utils.getdate(start), frappe.utils.getdate(end)
	if (end - start).days > 120:
		frappe.throw(_("Pick a shorter period."))
	team = teams.require_active_team()
	people = _people(team, frappe.utils.getdate()) or []
	names = dict(frappe.get_all("Employee", filters={"name": ["in", people or [""]]}, fields=["name", "employee_name"], as_list=True))
	absences = []
	if people and frappe.db.table_exists("Leave Application"):
		for leave in frappe.get_all(
			"Leave Application",
			filters={
				"employee": ["in", people],
				"docstatus": 1,
				"status": "Approved",
				"from_date": ["<=", end],
				"to_date": [">=", start],
			},
			fields=["employee", "from_date", "to_date", "half_day", "half_day_date"],
		):
			absences.append(
				{
					"employee": leave.employee,
					"employee_name": names.get(leave.employee, leave.employee),
					"from_date": leave.from_date,
					"to_date": leave.to_date,
					"half_day_date": leave.half_day_date if leave.half_day else None,
				}
			)
	holidays = {}
	for employee in people:
		holiday_list = employee_holiday_list(employee)
		if not holiday_list:
			continue
		for row in frappe.get_all(
			"Holiday",
			filters={"parent": holiday_list, "holiday_date": ["between", [start, end]], "weekly_off": 0},
			fields=["holiday_date", "description"],
		):
			entry = holidays.setdefault(
				(row.holiday_date, frappe.utils.strip_html_tags(row.description or "")),
				{"date": row.holiday_date, "description": frappe.utils.strip_html_tags(row.description or ""), "people": []},
			)
			entry["people"].append(names.get(employee, employee))
	return {"absences": absences, "holidays": sorted(holidays.values(), key=lambda h: h["date"])}


# --- Team ideas (#1980) -----------------------------------------------------------------------


@frappe.whitelist()
@_require_access
def get_team_ideas():
	"""Ideas shared with the active team, most votes first, with my vote and (if the setting
	allows) the author. The same vote as the company's, read by the team only."""
	from phamos.api import personal_ideas

	team = teams.require_active_team()
	return {"team": team, "ideas": personal_ideas._vote_rows(personal_ideas._readable_open_ideas({"team": team}))}


@frappe.whitelist()
@_require_access
def get_idea_for_vote(name):
	"""One shared idea: its text and the vote (personal_ideas checks who may read it)."""
	from phamos.api import personal_ideas

	return personal_ideas.get_idea_for_vote(name)


@frappe.whitelist(methods=["POST"])
@_require_access
def vote_idea(name):
	"""Toggle my upvote on a team idea."""
	from phamos.api import personal_ideas

	return personal_ideas.vote_idea(name)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_team_idea(title):
	"""A new idea of mine, shared with the active team right away. I write it out in my Personal
	Cockpit; only I edit it."""
	from phamos.api import personal_ideas

	doc = personal_ideas.create_idea(title=title)
	return personal_ideas.share_idea_with_team(doc["name"], teams.require_active_team())


@frappe.whitelist()
@_require_access
def get_idea_chat(name):
	"""The Raven chat of a team idea (IssueChatButton calls get_<doctype>_chat)."""
	from phamos.api import personal_ideas

	return personal_ideas.get_idea_chat(name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_idea_chat(name):
	"""Start or join the chat of a team idea; only those who may read it join."""
	from phamos.api import personal_ideas

	return personal_ideas.ensure_idea_chat(name)
