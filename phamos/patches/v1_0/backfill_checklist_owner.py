"""Backfill Checklist.checklist_owner for records created before it became required.

checklist_owner is reqd on the DocType and Checklist.validate() throws when it is
empty, so any Checklist predating that change fails to save in both the SPA and the
legacy Desk dialog. Fill it from the record's own creator, falling back to
Administrator when that user is gone or disabled -- validate() rejects those too.

Two bulk statements rather than a row loop: sites carrying years of Checklists would
otherwise spend one round-trip per record while migrate holds the site down.
"""

import frappe
from frappe.query_builder.functions import IfNull


def execute():
	checklist = frappe.qb.DocType("Checklist")
	user = frappe.qb.DocType("User")

	# Empty covers both NULL and "": rows predating the field are NULL, rows saved
	# through older SPA builds can be "".
	is_empty = IfNull(checklist.checklist_owner, "") == ""

	enabled_users = frappe.qb.from_(user).select(user.name).where(user.enabled == 1)

	(
		frappe.qb.update(checklist)
		.set(checklist.checklist_owner, checklist.owner)
		.where(is_empty & checklist.owner.isin(enabled_users))
	).run()

	# Whatever is left was created by a user who has since been deleted or disabled.
	(
		frappe.qb.update(checklist)
		.set(checklist.checklist_owner, "Administrator")
		.where(is_empty)
	).run()
