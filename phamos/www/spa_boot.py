# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Shared boot payload helpers for the cockpit SPAs."""

from contextlib import suppress

import frappe
from frappe.translate import get_parent_language, get_translations_from_apps, get_user_translations
from frappe.utils import cint, get_system_timezone


def get_spa_boot(default_route):
	"""Boot dict for Vite SPAs (csrf, timezone, user, language and its translations).

	`lang` and `__messages` mirror what Desk boots with, so `__()` in the SPAs (spa_shared/utils/
	i18n.js) translates like `__()` in Desk (#1605). English needs no table.
	"""
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
			"__messages": spa_translations(lang),
			"user": {
				"name": frappe.session.user,
				"full_name": frappe.utils.get_fullname(),
			},
		}
	)


def spa_translations(lang):
	"""Translations the SPAs need: phamos's own table plus the site's Translation records.

	Not Desk's full table (all apps, about 1.6 MB for German): the SPAs only show phamos strings,
	so common words they need belong in phamos/translations/<lang>.csv. Site translations still
	override, as in Desk.
	"""
	if not lang or lang == "en":
		return {}
	parent = get_parent_language(lang)
	messages = dict(get_translations_from_apps(parent, apps=["phamos"])) if parent else {}
	messages.update(get_translations_from_apps(lang, apps=["phamos"]))
	with suppress(Exception):
		if parent:
			messages.update(get_user_translations(parent))
		messages.update(get_user_translations(lang))
	return messages
