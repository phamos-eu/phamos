# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from phamos.www.spa_boot import get_spa_boot
from phamos.api.hr_spa import check_app_permission

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/hr-cockpit"
		raise frappe.Redirect

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access HR"), frappe.PermissionError)

	csrf_token = frappe.sessions.get_csrf_token()
	frappe.db.commit()  # nosemgrep
	context = frappe._dict()
	context.csrf_token = csrf_token
	context.boot = frappe.as_json(get_boot())
	context.site_name = frappe.local.site
	return context


@frappe.whitelist(methods=["POST"], allow_guest=True)
def get_context_for_dev():
	if not frappe.conf.developer_mode:
		frappe.throw(_("This method is only meant for developer mode"))
	return get_boot()


def get_boot():
	return get_spa_boot("/hr-cockpit")


