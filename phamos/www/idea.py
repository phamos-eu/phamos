# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Idea Catcher (#2200): the phone page that catches an idea in one step. Logic: phamos.api.idea_catcher."""

import os

import frappe
from frappe import _

from phamos.api.idea_catcher import ai_suggestions_enabled
from phamos.cockpits.permissions import is_colleague
from phamos.www.spa_boot import spa_translations

no_cache = 1

ASSET_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "idea")


def asset_version():
	"""Changes with the files, so phones load the new script after an update."""
	return int(max(os.path.getmtime(os.path.join(ASSET_DIR, name)) for name in ("idea.js", "idea.css")))


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/idea"
		raise frappe.Redirect

	if not is_colleague():
		frappe.throw(_("Only colleagues can catch ideas."), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	lang = frappe.local.lang or "en"
	context = frappe._dict()
	context.csrf_token = csrf_token
	context.lang = lang
	context.asset_version = asset_version()
	# Goes into a <script> block: "</" is escaped so no translation text can close the tag.
	context.boot = frappe.as_json(
		{
			"user": frappe.session.user,
			"lang": lang,
			"__messages": spa_translations(lang),
			"ai_suggestions": ai_suggestions_enabled(),
		}
	).replace("</", "<\\/")
	return context
