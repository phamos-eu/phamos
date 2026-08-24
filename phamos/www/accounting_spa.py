# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import cint, get_system_timezone
from phamos.api.accounting_spa import check_app_permission

no_cache = 1


def get_context(context):
	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/accounting-cockpit"
		raise frappe.Redirect

	if not check_app_permission():
		frappe.throw(_("You do not have permission to access Accounting"), frappe.PermissionError)

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
	tz = {
		"system": get_system_timezone(),
		"user": frappe.db.get_value("User", frappe.session.user, "time_zone")
		or get_system_timezone(),
	}
	return frappe._dict(
		{
			"frappe_version": frappe.__version__,
			"default_route": "/accounting-cockpit",
			"site_name": frappe.local.site,
			"socketio_port": frappe.conf.socketio_port,
			"csrf_token": frappe.sessions.get_csrf_token(),
			"setup_complete": cint(frappe.get_system_settings("setup_complete")),
			"sysdefaults": frappe.defaults.get_defaults(),
			"timezone": tz,
			"time_zone": tz,
			"user": {
				"name": frappe.session.user,
				"full_name": frappe.utils.get_fullname(),
			},
		}
	)
