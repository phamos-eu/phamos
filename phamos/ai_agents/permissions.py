# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Who may change which agent's AI Skills (#2225).

The Issue Assistant Trainer role reads and writes AI Skill, but only the Issue Assistant's: its
suggestions are what trainers accept, edit or dismiss. Reading or changing the Issue Assistant's skills
needs that role or System Manager, so the Accounting roles don't see them (they quote customers' Issues). AI agents never accept their own
suggestions (checked in phamos/ai_agents/feedback.py).
"""

import frappe

TRAINER_ROLE = "Issue Assistant Trainer"
ACCOUNTING_ROLES = {"Accounts Manager", "Accounts User", "AI Accountant"}


def _issue_agent():
	from phamos.setup.issue_assistant import ASSISTANT_NAME

	return ASSISTANT_NAME


def _trainer_only(roles):
	return TRAINER_ROLE in roles and not roles & ACCOUNTING_ROLES


def ai_skill_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles:
		return True
	if doc.get("agent") == _issue_agent():
		# its suggestions quote customers' Issues: trainers (and System Manager) only, also for reading (#2226)
		return TRAINER_ROLE in roles
	return not _trainer_only(roles)


def ai_skill_query(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or "System Manager" in roles or not _trainer_only(roles):
		return ""
	return f"`tabAI Skill`.agent = {frappe.db.escape(_issue_agent())}"


def ai_agent_run_has_permission(doc, ptype=None, user=None, debug=False):
	"""Trainers read the Issue Assistant's runs, not the Accounting ones (AI review on !1392)."""
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	roles = set(frappe.get_roles(user))
	if "System Manager" in roles or not _trainer_only(roles):
		return True
	return doc.get("agent") == _issue_agent()


def ai_agent_run_query(user=None):
	user = user or frappe.session.user
	roles = set(frappe.get_roles(user))
	if user == "Administrator" or "System Manager" in roles or not _trainer_only(roles):
		return ""
	return f"`tabAI Agent Run`.agent = {frappe.db.escape(_issue_agent())}"
