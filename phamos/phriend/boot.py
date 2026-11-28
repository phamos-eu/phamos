# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import cint

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
	}


# Phriend Settings → Features: one switch per feature (#2008); the companion slices add theirs.
FEATURE_FIELDS = ("reactions", "quiet_mode", "one_voice", "events", "easter_eggs", "rate_fixes")


def features(settings):
	"""The feature switches for Desk and the cockpits, {"reactions": 1, …}."""
	return {field: 1 if cint(settings.get(field)) else 0 for field in FEATURE_FIELDS}


def _may_open_implementation_cockpit():
	from phamos.api.implementation_cockpit import has_internal_access, is_internal_user

	return is_internal_user() and has_internal_access()


def app_versions():
	"""{app: version}, as Desk has it in frappe.boot.versions; for the cockpits and the website.

	From each app's __version__, not frappe.utils.change_log.get_versions(): that runs git for
	every app, which Desk pays once per session but the cockpits would pay on every page load.
	"""
	versions = {}
	for app in frappe.get_installed_apps():
		try:
			versions[app] = getattr(frappe.get_module(app), "__version__", "") or ""
		except Exception:
			# a broken app must not take the page down; Phriend just omits its version
			versions[app] = ""
	return versions


def web_boot():
	"""Phriend on the website pages (#2104): what phriend_boot() gives Desk, plus the app versions.

	Only for Desk users (user type System User), not for portal logins (Website User), even
	with an empty Allowed role (PM, 2026-11-23). None when Phriend is not for the user.
	"""
	if frappe.session.user == "Guest":
		return None
	if frappe.get_cached_value("User", frappe.session.user, "user_type") != "System User":
		return None
	boot = phriend_boot()
	if not boot:
		return None
	versions = app_versions()
	lang = frappe.local.lang or "en"
	return {
		**boot,
		"user": frappe.session.user,
		"versions": versions,
		# website pages carry no translations: the ball fetches Phriend's words once per language
		# and phamos version (get_web_translations) and keeps them in the browser
		"lang": lang,
		"messages_key": "" if lang == "en" else f"{lang}:{versions.get('phamos', '')}",
	}


def boot_session(bootinfo):
	"""Tell the desk whether Phriend shows up for this user (`frappe.boot.phriend`)."""
	boot = phriend_boot()
	if boot:
		bootinfo.phriend = boot
