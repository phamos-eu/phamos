"""Move the HR and PM cockpit settings to their spelled-out field names (#1453).

The cockpits are named after their area everywhere else (sales_, accounting_), so
hr_* becomes human_resources_* and pm_* becomes project_management_*. The saved
values move with them; the HR app on the Apps screen is renamed from hr_spa to
human_resources_spa, so users who picked it as their default app follow along.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

FIELDS = {
	"hr_department": "human_resources_department",
	"hr_timesheet_project": "human_resources_timesheet_project",
	"pm_department": "project_management_department",
	"pm_timesheet_project": "project_management_timesheet_project",
}


def execute():
	for old, new in FIELDS.items():
		rename_field("phamos Settings", old, new)

	frappe.db.set_value("User", {"default_app": "hr_spa"}, "default_app", "human_resources_spa")
	frappe.clear_cache(doctype="phamos Settings")
