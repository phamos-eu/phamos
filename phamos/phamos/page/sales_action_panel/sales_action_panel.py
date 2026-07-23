# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Action Panel — click-dummy APIs.

Real data wiring will replace the mock payload later.
Settings are stored on the Sales Action Panel Settings Single.
"""

import frappe
from frappe import _


@frappe.whitelist()
def get_settings():
	"""Return Sales Action Panel Settings used when starting work."""
	if not frappe.db.exists("DocType", "Sales Action Panel Settings"):
		return {"cost_center_project": None, "cost_center_project_name": None}

	doc = frappe.get_single("Sales Action Panel Settings")
	project = doc.cost_center_project
	project_name = None
	if project:
		project_name = frappe.db.get_value("Project", project, "project_name") or project
	return {
		"cost_center_project": project,
		"cost_center_project_name": project_name,
	}


@frappe.whitelist()
def save_settings(cost_center_project=None):
	"""Persist Cost Center Project for Start Work auto-select."""
	if not frappe.db.exists("DocType", "Sales Action Panel Settings"):
		frappe.throw(_("Sales Action Panel Settings doctype is not installed."))

	doc = frappe.get_single("Sales Action Panel Settings")
	doc.cost_center_project = cost_center_project or None
	doc.save(ignore_permissions=True)
	return get_settings()
