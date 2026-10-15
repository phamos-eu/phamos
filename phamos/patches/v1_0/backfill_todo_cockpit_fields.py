# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Fill the Personal Cockpit's ToDo fields for existing ToDos (phamos/phamos#1553).

- cockpit_closed_on / cockpit_closed_by for Closed and Cancelled ToDos: from the newest
  Version that changed the status to Closed/Cancelled; otherwise from modified/modified_by
  (ToDos closed through db_set have no Version). Earlier lead times are approximate.
- cockpit_first_due_date: the current due date (the original one is not recorded).
- cockpit_important: priority High.

Idempotent: only fills empty values. Runs before after_migrate, so it creates the fields first.
"""

import json

import frappe

from phamos.cockpits.setup import ensure_todo_fields

BATCH = 500


def execute():
	ensure_todo_fields()
	frappe.clear_cache(doctype="ToDo")

	from_version = from_modified = 0
	while True:
		rows = frappe.db.sql(
			"""SELECT name, modified, modified_by FROM `tabToDo`
			WHERE status IN ('Closed', 'Cancelled') AND cockpit_closed_on IS NULL
			LIMIT %s""",
			BATCH,
			as_dict=True,
		)
		if not rows:
			break
		closes = _closes_from_versions([r.name for r in rows])
		for row in rows:
			when, by = closes.get(row.name) or (row.modified, row.modified_by)
			if row.name in closes:
				from_version += 1
			else:
				from_modified += 1
			frappe.db.set_value(
				"ToDo",
				row.name,
				{"cockpit_closed_on": when, "cockpit_closed_by": by},
				update_modified=False,
			)
		frappe.db.commit()

	frappe.db.sql(
		"""UPDATE `tabToDo` SET cockpit_first_due_date = `date`
		WHERE cockpit_first_due_date IS NULL AND `date` IS NOT NULL"""
	)
	frappe.db.sql(
		"""UPDATE `tabToDo` SET cockpit_important = 1
		WHERE priority = 'High' AND IFNULL(cockpit_important, 0) = 0"""
	)
	print(f"ToDo closed-on backfill: {from_version} from Version history, {from_modified} from modified.")


def _closes_from_versions(names):
	"""Map ToDo name -> (creation, owner) of the newest Version that closed or cancelled it."""
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": "ToDo", "docname": ("in", names), "data": ("like", '%"status"%')},
		fields=["docname", "data", "creation", "owner"],
		order_by="creation asc",
	)
	closes = {}
	for version in versions:
		try:
			changed = json.loads(version.data or "{}").get("changed") or []
		except ValueError:
			continue
		for change in changed:
			if len(change) == 3 and change[0] == "status" and change[2] in ("Closed", "Cancelled"):
				closes[version.docname] = (version.creation, version.owner)
	return closes
