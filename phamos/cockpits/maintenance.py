# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Housekeeping for data the Cockpits module attaches to ToDos (#1554)."""

import frappe


def cleanup_orphan_todo_checklists():
	"""Delete Checklists whose ToDo no longer exists.

	Frappe deletes assignment ToDos with raw SQL when their record is deleted
	(`delete_dynamic_links`), which skips the ToDo on_trash hook.
	"""
	orphans = frappe.db.sql(
		"""SELECT c.name FROM `tabChecklist` c
		LEFT JOIN `tabToDo` t ON t.name = c.reference_record
		WHERE c.document = 'ToDo' AND t.name IS NULL""",
		pluck=True,
	)
	for name in orphans:
		frappe.delete_doc("Checklist", name, ignore_permissions=True, force=True)
	if orphans:
		frappe.db.commit()
	return len(orphans)
