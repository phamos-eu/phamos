# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Who belongs to which Team, and which Team a user's Team Cockpit shows (#1955).

A user belongs to a Team when their Employee has a Team Assignment open today (#1974), or, for a
team without assignments, is its lead, co-lead or one of its members. The
Team doctype itself stays System Manager only: the Team Cockpit reads it through this module,
which decides who may see which team.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

from phamos.phamos.doctype.team_assignment.team_assignment import has_assignments
from phamos.setup.general_management import GENERAL_MANAGEMENT_ROLE

# These roles steer the whole company, so they may open every team.
ALL_TEAMS_ROLES = ("System Manager", GENERAL_MANAGEMENT_ROLE)
# User default holding the team the Team Cockpit shows; it follows the user across browsers.
ACTIVE_TEAM_KEY = "cockpit_active_team"


def _employee(user):
	return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def sees_all_teams(user=None):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(ALL_TEAMS_ROLES))


def member_teams(user=None, on_date=None):
	"""Names of the teams `user` is lead, co-lead or member of on `on_date` (default today), sorted.

	From the Team Assignments open that day (#1974). A team without any assignment (not migrated,
	or created outside Team Assignment) still counts through the Team's own lead, co-lead and member
	fields.
	"""
	user = user or frappe.session.user
	employee = _employee(user)
	if not employee:
		return []
	on_date = getdate(on_date or today())
	names = set(
		frappe.get_all(
			"Team Assignment",
			filters={"employee": employee, "from_date": ["<=", on_date]},
			or_filters=[["until_date", "is", "not set"], ["until_date", ">=", on_date]],
			pluck="team",
			limit_page_length=0,
		)
	)
	names.update(team for team in _legacy_member_teams(employee) if not has_assignments(team))
	return sorted(names)


def _legacy_member_teams(employee):
	"""Teams naming `employee` in their own lead, co-lead or member fields."""
	names = set(
		frappe.get_all(
			"Team",
			or_filters=[["team_lead", "=", employee], ["co_team_lead", "=", employee]],
			pluck="name",
			limit_page_length=0,
		)
	)
	names.update(
		frappe.get_all(
			"Team Members",
			filters={"employee": employee, "parenttype": "Team", "parentfield": "team_members"},
			pluck="parent",
			limit_page_length=0,
		)
	)
	return names


def available_teams(user=None):
	"""Names of the teams `user` may open in the Team Cockpit, sorted. Guests get none."""
	user = user or frappe.session.user
	if not user or user == "Guest":
		return []
	if sees_all_teams(user):
		return frappe.get_all("Team", pluck="name", order_by="name asc", limit_page_length=0)
	return member_teams(user)


def active_team(user=None):
	"""The team the Team Cockpit shows for `user`: their stored choice while they may still open
	it, otherwise their first team. None for a user with no team."""
	user = user or frappe.session.user
	teams = available_teams(user)
	if not teams:
		return None
	stored = frappe.defaults.get_user_default(ACTIVE_TEAM_KEY, user=user)
	return stored if stored in teams else teams[0]


def require_active_team():
	team = active_team()
	if not team:
		frappe.throw(_("You are not a member of any team."), frappe.PermissionError)
	return team


def set_active_team(team):
	"""Store `team` as the session user's active team. Only a team they may open."""
	if team not in available_teams():
		frappe.throw(_("You are not a member of team {0}.").format(team), frappe.PermissionError)
	frappe.defaults.set_user_default(ACTIVE_TEAM_KEY, team)
	return team


def team_users(team):
	"""Enabled System Users of the team's lead, co-lead and members: name, full_name, user_image."""
	doc = frappe.get_doc("Team", team)
	employees = [doc.team_lead, doc.co_team_lead] + [row.employee for row in doc.team_members]
	employees = list(dict.fromkeys(e for e in employees if e))
	if not employees:
		return []
	user_ids = frappe.get_all(
		"Employee",
		filters={"name": ("in", employees), "status": "Active", "user_id": ("is", "set")},
		pluck="user_id",
		limit_page_length=0,
	)
	if not user_ids:
		return []
	users = frappe.get_all(
		"User",
		filters={"name": ("in", user_ids), "enabled": 1, "user_type": "System User"},
		fields=["name", "full_name", "user_image"],
		order_by="full_name asc",
		limit_page_length=0,
	)
	return [{"name": u.name, "full_name": u.full_name or u.name, "user_image": u.user_image} for u in users]


def team_projects(team):
	"""Projects of the team's Implementations (Project.custom_implementation -> Implementation.team).

	Project.custom_implementation exists on the sites but is not created by this app, hence the
	meta check.
	"""
	if not frappe.get_meta("Project").has_field("custom_implementation"):
		return []
	implementations = frappe.get_all(
		"Implementation", filters={"team": team}, pluck="name", limit_page_length=0
	)
	if not implementations:
		return []
	return frappe.get_all(
		"Project",
		filters={"custom_implementation": ("in", implementations)},
		pluck="name",
		limit_page_length=0,
	)
