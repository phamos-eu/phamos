"""Move the per-cockpit settings from phamos Settings to Cockpit Settings (phamos/phamos#1932).

The fields keep their names. Their values stay in `tabSingles` under "phamos Settings" after the
fields left that DocType's JSON, so they are read from there. A value already set on Cockpit
Settings is never overwritten. Safe to run twice.
"""

import frappe

OLD = "phamos Settings"
NEW = "Cockpit Settings"

FIELDS = (
	"human_resources_department",
	"human_resources_timesheet_project",
	"human_resources_privacy_reveal_seconds",
	"personal_ideas_show_author",
	"project_management_department",
	"project_management_timesheet_project",
	"sales_department",
	"sales_standard_project",
	"accounting_department",
	"accounting_standard_project",
	"software_development_department",
	"software_development_timesheet_project",
)

TABLE_FIELD = "human_resources_sick_leave_types"
TABLE_DOCTYPE = "Sick Leave Type Item"


def execute():
	frappe.reload_doc("cockpits", "doctype", "cockpit_settings")
	meta = frappe.get_meta(NEW)
	for field in FIELDS:
		_move_value(field, meta.get_field(field).default)
	_move_table_rows()
	frappe.db.delete("Singles", {"doctype": OLD, "field": ("in", FIELDS)})
	frappe.clear_cache(doctype=NEW)


def _stored(doctype, field):
	"""The (value,) row for a Single's field, or None when the field has no row.

	tabSingles has no `name` column, so frappe.db.exists can't tell; ask the table directly.
	"""
	rows = frappe.db.sql("select value from `tabSingles` where doctype = %s and field = %s", (doctype, field))
	return rows[0] if rows else None


def _move_value(field, default):
	if _stored(NEW, field):
		return
	old = _stored(OLD, field)
	if old:
		value = old[0]
	elif default is not None:
		# never stored on phamos Settings either: a missing row reads as 0 / empty, not as the default
		value = default
	else:
		return
	frappe.db.set_single_value(NEW, field, value, update_modified=False)


def _move_table_rows():
	old_filters = {"parenttype": OLD, "parent": OLD, "parentfield": TABLE_FIELD}
	if frappe.db.exists(TABLE_DOCTYPE, {"parenttype": NEW, "parent": NEW, "parentfield": TABLE_FIELD}):
		frappe.db.delete(TABLE_DOCTYPE, old_filters)
		return
	for name in frappe.get_all(TABLE_DOCTYPE, filters=old_filters, pluck="name"):
		frappe.db.set_value(TABLE_DOCTYPE, name, {"parenttype": NEW, "parent": NEW}, update_modified=False)
