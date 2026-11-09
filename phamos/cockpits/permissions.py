# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Private Cockpits records (#1556, #1557, #1559, #1771): a user sees only their own, System Managers included.

Personal productivity data is nobody else's business (works council, GDPR). Administrator
keeps access for support and data requests.

One exception (#1842): an idea its owner handed in for a vote is readable by everyone. Its
history (Version rows) and writing sessions stay private, and only the owner may change it.
"""

import frappe

from phamos.cockpits.defaults import IDEA_VOTE_OPEN


def _private(user):
	return (user or frappe.session.user) != "Administrator"


def focus_session_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return f"`tabFocus Session`.`user` = {frappe.db.escape(user)}"


def focus_session_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user):
		return True
	return doc.user == user


def todo_challenge_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return f"`tabToDo Challenge`.`user` = {frappe.db.escape(user)}"


def todo_challenge_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user):
		return True
	return doc.user == user


def day_plan_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return f"`tabDay Plan`.`user` = {frappe.db.escape(user)}"


def day_plan_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user):
		return True
	return doc.user == user


def idea_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return (
		f"(`tabIdea`.`user` = {frappe.db.escape(user)}"
		f" or `tabIdea`.`vote_status` = {frappe.db.escape(IDEA_VOTE_OPEN)})"
	)


def idea_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user) or doc.user == user:
		return True
	# Handed in for a vote: everyone may read it; only the owner changes it.
	return doc.get("vote_status") == IDEA_VOTE_OPEN and (ptype or "read") in ("read", "select")


def is_colleague(user=None):
	"""A System User (or Administrator): who may see ideas up for vote (#1842). Website Users
	(portal customers) are logged in too, but are not colleagues."""
	user = user or frappe.session.user
	if user in (None, "Guest"):
		return False
	return user == "Administrator" or frappe.get_cached_value("User", user, "user_type") == "System User"


def can_read_idea(name, user=None):
	"""Whether the user may read the idea the way the cockpit shows it: their own, or one handed in
	for a vote when they are a colleague (System User). Ideas have role permissions for System
	Manager only, so frappe.has_permission says no to most employees; the cockpit API and the
	idea's Raven chat (#1842) go by this rule instead."""
	user = user or frappe.session.user
	if not _private(user):
		return True
	idea = frappe.db.get_value("Idea", name, ["user", "vote_status"], as_dict=True)
	if not idea:
		return False
	if idea.user == user:
		return True
	return idea.vote_status == IDEA_VOTE_OPEN and is_colleague(user)


def idea_vote_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return f"`tabIdea Vote`.`user` = {frappe.db.escape(user)}"


def idea_vote_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user):
		return True
	return doc.user == user


def idea_writing_session_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	return f"`tabIdea Writing Session`.`user` = {frappe.db.escape(user)}"


def idea_writing_session_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user):
		return True
	return doc.user == user


# The Version rows of an idea carry its full text, and Version is readable by every System
# Manager. Only rows of Idea and Idea Writing Session are narrowed; other Versions are untouched.
PRIVATE_VERSION_DOCTYPES = {"Idea": "tabIdea", "Idea Writing Session": "tabIdea Writing Session"}


def version_query(user=None):
	user = user or frappe.session.user
	if not _private(user):
		return ""
	me = frappe.db.escape(user)
	owned = " or ".join(
		f"(`tabVersion`.`ref_doctype` = {frappe.db.escape(doctype)} and `tabVersion`.`docname` in "
		f"(select `name` from `{table}` where `user` = {me}))"
		for doctype, table in PRIVATE_VERSION_DOCTYPES.items()
	)
	others = ", ".join(frappe.db.escape(d) for d in PRIVATE_VERSION_DOCTYPES)
	return f"(`tabVersion`.`ref_doctype` not in ({others}) or {owned})"


def version_has_permission(doc, ptype=None, user=None):
	user = user or frappe.session.user
	if not _private(user) or doc.ref_doctype not in PRIVATE_VERSION_DOCTYPES:
		return True
	return frappe.db.get_value(doc.ref_doctype, doc.docname, "user") == user
