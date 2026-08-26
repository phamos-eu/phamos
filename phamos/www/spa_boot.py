# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Shared boot payload helpers for department / I Own My Work SPAs."""

import frappe
from frappe.translate import get_all_translations
from frappe.utils import cint, get_system_timezone


def get_spa_boot(default_route):
	"""Boot dict for Vite SPAs (csrf, timezone, translations)."""
	lang = frappe.local.lang or "en"
	tz = {
		"system": get_system_timezone(),
		"user": frappe.db.get_value("User", frappe.session.user, "time_zone")
		or get_system_timezone(),
	}
	return frappe._dict(
		{
			"frappe_version": frappe.__version__,
			"default_route": default_route,
			"site_name": frappe.local.site,
			"socketio_port": frappe.conf.socketio_port,
			"csrf_token": frappe.sessions.get_csrf_token(),
			"setup_complete": cint(frappe.get_system_settings("setup_complete")),
			"sysdefaults": frappe.defaults.get_defaults(),
			"timezone": tz,
			"time_zone": tz,
			"lang": lang,
			"__messages": get_all_translations(lang),
			"user": {
				"name": frappe.session.user,
				"full_name": frappe.utils.get_fullname(),
			},
		}
	)
