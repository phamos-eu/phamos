# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe

from phamos.phriend.shortcut import site_shortcut, user_shortcut


def is_for_user():
	"""Whether Phriend shows up for the current user: not Guest, Phriend switched on, and the
	allowed role (if one is set)."""
	if frappe.session.user == "Guest":
		return False
	settings = frappe.get_cached_doc("Phriend Settings")
	if not settings.enabled:
		return False
	return not settings.allowed_role or settings.allowed_role in frappe.get_roles()


def phriend_boot():
	"""What the Phriend ball needs at start, for Desk and the cockpits alike (#1900).

	{"enabled": 1, "shortcut": …, "default_shortcut": …} when Phriend shows up for the current
	user, None otherwise (Guest, Phriend switched off, or the user lacks the allowed role).
	"""
	if not is_for_user():
		return None
	# the user's own shortcut ("" when switched off) and the site's, for "Back to the default"
	return {"enabled": 1, "shortcut": user_shortcut(), "default_shortcut": site_shortcut()}


def boot_session(bootinfo):
	"""Tell the desk whether Phriend shows up for this user (`frappe.boot.phriend`)."""
	boot = phriend_boot()
	if boot:
		bootinfo.phriend = boot
