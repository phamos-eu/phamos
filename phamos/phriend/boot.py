# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe


def boot_session(bootinfo):
	"""Tell the desk whether Phriend shows up for this user (`frappe.boot.phriend`)."""
	if frappe.session.user == "Guest":
		return
	settings = frappe.get_cached_doc("Phriend Settings")
	if not settings.enabled:
		return
	if settings.allowed_role and settings.allowed_role not in frappe.get_roles():
		return
	bootinfo.phriend = {"enabled": 1}
