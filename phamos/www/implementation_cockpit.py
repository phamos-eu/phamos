# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from phamos.www.spa_boot import get_spa_boot, theme_color
from phamos.api.implementation_cockpit import has_internal_access, is_internal_user

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/implementation-cockpit"
		raise frappe.Redirect

	# Staff need the cockpit role. Customers may always open the page: without a shared
	# implementation the cockpit shows "No implementation shared with you yet" instead of an
	# error. The data endpoints check the scope themselves; the Apps screen keeps the stricter
	# check_app_permission.
	if is_internal_user() and not has_internal_access():
		frappe.throw(
			_("You do not have permission to access the Implementation Cockpit"), frappe.PermissionError
		)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	context = frappe._dict()
	context.csrf_token = csrf_token
	boot = get_boot()
	context.boot = frappe.as_json(boot)
	context.theme_color = theme_color(boot)
	context.site_name = frappe.local.site
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	boot = get_spa_boot("/implementation-cockpit")
	if not is_internal_user():
		# Customers don't report through Phriend yet (#1898 scope, #1938); no ball, no app versions.
		boot.phriend = None
		boot.versions = {}
	return boot
