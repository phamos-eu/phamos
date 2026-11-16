"""Phriend report type "Idea" is now "Improvement" (phamos/phamos#1924).

"Idea" read as "this creates an Idea" (the Personal Cockpit doctype); it only ever made a support Issue.
Moves the Report Type of existing Issues over. Their subjects ("[Idea] ...") stay as they were written.
The field's options are updated by ``after_migrate``, which runs after the patches; the update here does
not need them.
"""

import frappe


def execute():
	if not frappe.db.has_column("Issue", "phriend_type"):
		return
	frappe.db.sql("update `tabIssue` set `phriend_type` = 'Improvement' where `phriend_type` = 'Idea'")
