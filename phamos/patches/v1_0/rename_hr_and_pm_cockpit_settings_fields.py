"""Move the HR and PM cockpit settings to their spelled-out field names (#1453).

The cockpits are named after their area everywhere else (sales_, accounting_), so
hr_* becomes human_resources_* and pm_* becomes project_management_*. The saved
values move with them; the HR app on the Apps screen is renamed from hr_spa to
human_resources_spa, so users (and System Settings) that picked it as the default app
follow along.
"""

import frappe
from frappe.model.utils.rename_field import rename_field

SETTINGS_DOCTYPE = "phamos Settings"

FIELDS = {
	"hr_department": "human_resources_department",
	"hr_timesheet_project": "human_resources_timesheet_project",
	"pm_department": "project_management_department",
	"pm_timesheet_project": "project_management_timesheet_project",
}

OLD_APP_NAME = "hr_spa"
NEW_APP_NAME = "human_resources_spa"


def execute():
	"""Move saved phamos Settings values and default-app choices to the new names.

	Side effects:
		- tabSingles rows of phamos Settings move from the old to the new fieldnames,
		  together with Property Setters, report columns and user list settings
		  (all handled by Frappe's rename_field).
		- User.default_app and System Settings default_app change from hr_spa to
		  human_resources_spa.

	Safe to run twice: a second run finds no old rows and changes nothing.
	"""
	_ensure_new_fields_exist()
	for old_fieldname, new_fieldname in FIELDS.items():
		rename_field(SETTINGS_DOCTYPE, old_fieldname, new_fieldname)

	_move_default_app()
	frappe.clear_cache(doctype=SETTINGS_DOCTYPE)


def _ensure_new_fields_exist():
	"""Stop the migration if the new fields are missing from phamos Settings.

	rename_field only prints a message and returns when the target field is missing.
	The patch would then be recorded as done and never run again, leaving the saved
	values stranded under the old fieldnames, so fail loudly instead.
	"""
	meta = frappe.get_meta(SETTINGS_DOCTYPE, cached=False)
	missing = [fieldname for fieldname in FIELDS.values() if not meta.has_field(fieldname)]
	if missing:
		frappe.throw(
			f"{SETTINGS_DOCTYPE} is missing {', '.join(missing)}; "
			"run this patch after the DocType has been synced (post_model_sync)."
		)


def _move_default_app():
	"""Point every default-app choice that used the old HR app name to the new one."""
	frappe.db.set_value(
		"User", {"default_app": OLD_APP_NAME}, "default_app", NEW_APP_NAME, update_modified=False
	)
	if frappe.db.get_single_value("System Settings", "default_app") == OLD_APP_NAME:
		frappe.db.set_single_value("System Settings", "default_app", NEW_APP_NAME)
