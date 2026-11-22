# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ophice (phamos/phamos#2069, #2070): the app people "go to work" in, at /ophice."""

import frappe
from frappe import _

from phamos.api.ophice import check_app_permission
from phamos.www.spa_boot import get_spa_boot, theme_color

no_cache = 1


def get_context(context):
	# The guest entry (#2082): open to everyone, with a small boot of its own.
	if _is_guest_page():
		return _guest_context()

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/ophice"
		raise frappe.Redirect

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Ophice"), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	context = frappe._dict()
	context.csrf_token = csrf_token
	boot = get_boot()
	context.boot = frappe.as_json(boot)
	context.theme_color = theme_color(boot)
	context.site_name = frappe.local.site
	return context


def _is_guest_page():
	path = (getattr(frappe.local, "request", None) and frappe.request.path) or ""
	return path.rstrip("/") == "/ophice/guest"


def _guest_context():
	"""What the guest page needs: language and its words, nothing about the office or the user."""
	from phamos.www.spa_boot import NEUTRAL_THEME_COLOR, spa_translations

	lang = frappe.local.lang or "en"
	boot = {
		"guest": True,
		"lang": lang,
		"__messages": spa_translations(lang),
		"site_name": frappe.local.site,
		"csrf_token": frappe.sessions.get_csrf_token(),
		"sysdefaults": {"time_format": "HH:mm", "date_format": "dd.mm.yyyy"},
	}
	context = frappe._dict()
	context.csrf_token = boot["csrf_token"]
	context.boot = frappe.as_json(boot)
	context.theme_color = NEUTRAL_THEME_COLOR
	context.site_name = frappe.local.site
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	return get_spa_boot("/ophice")
