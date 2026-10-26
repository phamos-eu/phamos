"""The Phamos Team table of phamos Settings is retired (phamos/phamos#1510): the website people
pages come from Person Web Profiles now. Frappe keeps a DocType whose folder was removed, and
drops the table only for custom doctypes, so both are removed here, after the model sync removed
the field from the settings.
"""

import frappe


def execute():
	frappe.delete_doc("DocType", "Phamos Team", ignore_missing=True, force=True)
	frappe.db.sql_ddl("drop table if exists `tabPhamos Team`")
