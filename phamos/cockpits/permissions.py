# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Private Cockpits records (#1556, #1557): a user sees only their own, System Managers included.

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
