# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""I Own My Work was replaced by the Personal Cockpit (phamos/phamos#1456).

Users (or the system) that chose I Own My Work as their default app would otherwise
land on /apps after login, because Frappe ignores an app name it no longer knows.
"""

import frappe

OLD_APP_NAME = "i_own_my_work"
NEW_APP_NAME = "personal_cockpit"


def execute():
	frappe.db.set_value(
		"User", {"default_app": OLD_APP_NAME}, "default_app", NEW_APP_NAME, update_modified=False
	)
	if frappe.db.get_single_value("System Settings", "default_app") == OLD_APP_NAME:
		frappe.db.set_single_value("System Settings", "default_app", NEW_APP_NAME)
