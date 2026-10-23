"""Marketing Event Response was a child table no doctype used anymore. Frappe keeps a DocType whose
folder was removed, so record and table are removed here (pattern: delete_phamos_team_doctype)."""

import frappe


def execute():
	frappe.delete_doc("DocType", "Marketing Event Response", ignore_missing=True, force=True)
	frappe.db.sql_ddl("drop table if exists `tabMarketing Event Response`")
