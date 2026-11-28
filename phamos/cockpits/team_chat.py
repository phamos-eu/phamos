# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The team chat's members follow the team (#1978).

One private Raven channel per Team (created when someone first opens the chat, through
`issue_chat.ensure_chat`). Its members are the users of the team's people today. When the Team
changes (a Team Assignment starts or ends, or the daily sync rewrites the Team), the people who
joined are added and those who left are removed; their messages stay. General Management and
System Manager may open every team's chat (decision 3 of #1978), so they are never removed.
"""

import frappe

from phamos.api import issue_chat
from phamos.cockpits import teams


def sync_team_channel(team):
	"""Add the team's people to its channel and remove everyone else (except those who see every
	team). Nothing to do while the team has no chat yet."""
	if not issue_chat.is_raven_installed() or not issue_chat.is_enabled():
		return
	channel = issue_chat.find_channel(issue_chat.TEAM_CHAT, team)
	if not channel:
		return
	wanted = [row["name"] for row in teams.team_users(team)]
	if wanted and channel.is_archived:
		# Raven archives a private channel when its last member leaves; a team with people again
		# gets its chat back
		issue_chat._set_archived(channel.name, False)
	issue_chat._ensure_members(channel, wanted)
	leavers = [
		user
		for user in issue_chat.channel_member_users(channel)
		if user not in wanted and not teams.sees_all_teams(user)
	]
	issue_chat._remove_members(channel, leavers)


def on_team_update(doc, method=None):
	"""Team on_update: membership may have changed. A failing chat sync must not undo the Team."""
	try:
		sync_team_channel(doc.name)
	except Exception:
		frappe.log_error(title=f"Team chat members of {doc.name} not updated")


def check_channel_member(doc, method=None):
	"""Raven Channel Member before_insert: only the team's people (and those who see every team)
	join a team's chat. Raven lets any member add others to a private channel; this keeps the team
	chat to the team (#1978). Bots and other channels are not touched."""
	linked_doctype, team = frappe.db.get_value("Raven Channel", doc.channel_id, ["linked_doctype", "linked_document"]) or (None, None)
	if linked_doctype != issue_chat.TEAM_CHAT or not team:
		return
	user, user_type = frappe.db.get_value("Raven User", doc.user_id, ["user", "type"]) or (None, None)
	if user_type != "User":
		return
	if teams.sees_all_teams(user) or user in {row["name"] for row in teams.team_users(team)}:
		return
	frappe.throw(frappe._("Only the people of team {0} can join its chat.").format(team), frappe.PermissionError)
