# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Private Cockpits records (#1556, #1557, #1559, #1771): a user sees only their own, System Managers included.

Personal productivity data is nobody else's business (works council, GDPR). Administrator
keeps access for support and data requests.
"""

import frappe


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
	return f"`tabIdea`.`user` = {frappe.db.escape(user)}"


def idea_has_permission(doc, ptype=None, user=None):
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
