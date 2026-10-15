# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Schema the Cockpits module adds to core doctypes, created in code (not fixtures).

Called from `after_migrate` and from the backfill patch (patches run before
`after_migrate`). Idempotent.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from phamos.cockpits.defaults import MODULE

# Convention: custom fields on standard doctypes live in one section "Implementation Specific",
# the very first section of the form, never collapsed: they matter most to this implementation's
# users. An empty insert_after puts the section above every standard field. This works because
# ToDo starts with a Section Break; a doctype that starts with a Tab Break or a plain field needs
# the section after that Tab Break, or a closing Section Break, so no standard field is swallowed.
IMPLEMENTATION_SECTION = "custom_implementation_specific"
# The section used to be called "Personal Cockpit" (fieldname cockpit_section, never released).
OBSOLETE_TODO_FIELDS = ("cockpit_section",)

TODO_FIELDS = [
	{
		"fieldname": IMPLEMENTATION_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
	},
	{
		"fieldname": "cockpit_closed_on",
		"label": "Closed On",
		"fieldtype": "Datetime",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": IMPLEMENTATION_SECTION,
		"description": "When the ToDo was closed or cancelled. Set automatically.",
	},
	{
		"fieldname": "cockpit_closed_by",
		"label": "Closed By",
		"fieldtype": "Link",
		"options": "User",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "cockpit_closed_on",
	},
	{
		"fieldname": "cockpit_important",
		"label": "Important",
		"fieldtype": "Check",
		"insert_after": "cockpit_closed_by",
		"description": "My own judgement of importance (Eisenhower). Starts from priority High.",
	},
	{
		"fieldname": "cockpit_column_break",
		"fieldtype": "Column Break",
		"insert_after": "cockpit_important",
	},
	{
		"fieldname": "cockpit_first_due_date",
		"label": "First Due Date",
		"fieldtype": "Date",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "cockpit_column_break",
	},
	{
		"fieldname": "cockpit_reschedule_count",
		"label": "Times Postponed",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"default": "0",
		"insert_after": "cockpit_first_due_date",
	},
	{
		"fieldname": "cockpit_estimate_minutes",
		"label": "Estimate (Minutes)",
		"fieldtype": "Int",
		"insert_after": "cockpit_reschedule_count",
	},
	{
		"fieldname": "cockpit_actual_minutes",
		"label": "Actual (Minutes)",
		"fieldtype": "Int",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "cockpit_estimate_minutes",
	},
	{
		"fieldname": "cockpit_resume_note",
		"label": "Where to Pick Up",
		"fieldtype": "Small Text",
		"no_copy": 1,
		"insert_after": "cockpit_actual_minutes",
	},
]


def ensure_module():
	if not frappe.db.exists("Module Def", MODULE):
		frappe.get_doc({"doctype": "Module Def", "module_name": MODULE, "app_name": "phamos"}).insert(
			ignore_permissions=True
		)


def ensure_todo_fields():
	ensure_module()
	for fieldname in OBSOLETE_TODO_FIELDS:
		if frappe.db.exists("Custom Field", {"dt": "ToDo", "fieldname": fieldname}):
			frappe.delete_doc("Custom Field", f"ToDo-{fieldname}", ignore_permissions=True, force=True)
	create_custom_fields({"ToDo": [{**field, "module": MODULE} for field in TODO_FIELDS]}, update=True)
	# A ToDo without a due date stays undated. Frappe's default "Today" made every ToDo
	# created without a date look due today. Assignments still pass today explicitly.
	# Created once; a later change by an administrator is kept.
	if not frappe.db.exists("Property Setter", {"doc_type": "ToDo", "field_name": "date", "property": "default"}):
		setter = make_property_setter("ToDo", "date", "default", "", "Text", validate_fields_for_doctype=False)
		frappe.db.set_value("Property Setter", setter.name, "module", MODULE)


def after_migrate():
	ensure_todo_fields()
