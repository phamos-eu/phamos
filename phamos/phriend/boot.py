# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe

from phamos.phriend.shortcut import site_shortcut, user_shortcut


def phriend_boot():
	"""What the Phriend ball needs at start, for Desk and the cockpits alike (#1900).

	{"enabled": 1, "shortcut": …, "default_shortcut": …} when Phriend shows up for the current
	user, None otherwise (Guest, Phriend switched off, or the user lacks the allowed role).
	"""
	if frappe.session.user == "Guest":
		return None
	settings = frappe.get_cached_doc("Phriend Settings")
	if not settings.enabled:
		return None
	if settings.allowed_role and settings.allowed_role not in frappe.get_roles():
		return None
	# the user's own shortcut ("" when switched off) and the site's, for "Back to the default"
	return {"enabled": 1, "shortcut": user_shortcut(), "default_shortcut": site_shortcut()}


def boot_session(bootinfo):
	"""Tell the desk whether Phriend shows up for this user (`frappe.boot.phriend`)."""
	boot = phriend_boot()
	if boot:
		bootinfo.phriend = boot
