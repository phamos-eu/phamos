# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Schema the Cockpits module adds to core doctypes, created in code (not fixtures).

Called from `after_migrate`. Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from phamos.cockpits.defaults import MODULE

# Convention: custom fields on standard doctypes live in one section "Implementation Specific",
# the very first section of the form, never collapsed: they matter most to this implementation's
# users. An empty insert_after puts the section above every standard field. A doctype that starts
# with a Tab Break or a plain field needs the section after that Tab Break, or a closing Section
# Break, so no standard field is swallowed.
IMPLEMENTATION_SECTION = "custom_implementation_specific"

# Task starts with plain fields (subject, project, issue), not a Section Break, so a closing
# Section Break keeps them out of our section (#1751).
TASK_FIELDS = [
	{
		"fieldname": IMPLEMENTATION_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
	},
	{
		"fieldname": "custom_task_owner",
		"label": "Task Owner",
		"fieldtype": "Link",
		"options": "User",
		"insert_after": IMPLEMENTATION_SECTION,
		"description": "Who is responsible for this task. Separate from assignment.",
	},
	{
		"fieldname": "custom_implementation_specific_end",
		"fieldtype": "Section Break",
		"insert_after": "custom_task_owner",
	},
]


def ensure_module():
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "phamos"}).insert(
			ignore_permissions=True
		)


def ensure_task_fields():
	ensure_module()
	create_custom_fields({"Task": [{**field, "module": MODULE} for field in TASK_FIELDS]}, update=True)


def after_migrate():
	ensure_task_fields()
