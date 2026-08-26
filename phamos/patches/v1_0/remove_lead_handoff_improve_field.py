"""Remove Lead Handoff Improve Field leftovers after CRM handoff was dropped from the MR.

Sites that migrated while that child DocType / Settings fields existed keep the DB
rows even though the JSON and Python module are gone, which breaks get_doc on
phamos Settings (Desk Workspaces/HR via get_popup_doctypes).
"""

import frappe


_SETTINGS_FIELDS = (
	"lead_handoff_improve_fields",
	"lead_handoff_auto_create_min_score",
	"lead_scan_section",
	"lead_scan_tab",
)


def execute():
	if frappe.db.table_exists("Lead Handoff Improve Field"):
		frappe.db.sql("delete from `tabLead Handoff Improve Field`")

	for fieldname in _SETTINGS_FIELDS:
		frappe.db.delete(
			"DocField",
			{"parent": "phamos Settings", "fieldname": fieldname},
		)

	frappe.db.sql(
		"delete from `tabSingles` where doctype=%s and field=%s",
		("phamos Settings", "lead_handoff_auto_create_min_score"),
	)

	if frappe.db.exists("DocType", "Lead Handoff Improve Field"):
		frappe.delete_doc("DocType", "Lead Handoff Improve Field", force=1, ignore_permissions=True)

	# delete_doc can leave the physical table behind when the controller is already gone
	if frappe.db.table_exists("Lead Handoff Improve Field"):
		frappe.db.sql_ddl("drop table if exists `tabLead Handoff Improve Field`")

	frappe.reload_doc("phamos", "doctype", "phamos_settings", force=True)
	frappe.clear_cache(doctype="phamos Settings")
