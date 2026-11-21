# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint

from phamos.phriend.feedback import open_requests as open_feedback
from phamos.phriend.quiet import state as quiet_state
from phamos.phriend.shortcut import site_shortcut, user_shortcut
from phamos.phriend.voice import state as voice_state


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

	{"enabled": 1, "shortcut": …, "default_shortcut": …, "has_target": 0|1, "features": {…}} when Phriend shows up for the current
	user, None otherwise (Guest, Phriend switched off, or the user lacks the allowed role).
	"""
	if not is_for_user():
		return None
	settings = frappe.get_cached_doc("Phriend Settings")
	on = features(settings)
	# the user's own shortcut ("" when switched off) and the site's, for "Back to the default";
	# has_target: reports go to another system, so there are none here to count
	return {
		"enabled": 1,
		"shortcut": user_shortcut(),
		"default_shortcut": site_shortcut(),
		"has_target": 1 if settings.target_url else 0,
		# "Status in the Implementation Cockpit" in the report flow (#1671)
		"implementation_cockpit": 1 if _may_open_implementation_cockpit() else 0,
		"features": on,
		# leave me in peace (#2010): the user's quiet time and warning mute, while the feature is on
		"quiet": quiet_state() if on["quiet_mode"] else None,
		# the menu links to Phriend Settings for those who may change them
		"can_configure": 1 if frappe.has_permission("Phriend Settings", "write") else 0,
		# one voice (#2011): today's unprompted bubbles, while the feature is on
		"voice": voice_state(settings) if on["one_voice"] else None,
		# rating a fix (#2014): the user's open rating questions
		"feedback": open_feedback() if on["rate_fixes"] else None,
	}


# Phriend Settings → Features: one switch per feature (#2008); the companion slices add theirs.
FEATURE_FIELDS = ("reactions", "quiet_mode", "one_voice", "events", "easter_eggs", "rate_fixes")


def features(settings):
	"""The feature switches for Desk and the cockpits, {"reactions": 1, …}."""
	return {field: 1 if cint(settings.get(field)) else 0 for field in FEATURE_FIELDS}


def _may_open_implementation_cockpit():
	from phamos.api.implementation_cockpit import has_internal_access, is_internal_user

	return is_internal_user() and has_internal_access()


def boot_session(bootinfo):
	"""Tell the desk whether Phriend shows up for this user (`frappe.boot.phriend`)."""
	boot = phriend_boot()
	if boot:
		bootinfo.phriend = boot
