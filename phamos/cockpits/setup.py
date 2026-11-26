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
		"fieldname": "custom_team",
		"label": "Team",
		"fieldtype": "Link",
		"options": "Team",
		"insert_after": "custom_task_owner",
		"description": "The team this task belongs to. It shows in that team's Team Cockpit.",
	},
	{
		"fieldname": "custom_implementation_specific_end",
		"fieldtype": "Section Break",
		"insert_after": "custom_team",
	},
]

# On Issue the section shows on every Issue and starts with the team (#1955). Phriend's fields
# follow the team inside it and carry their own conditions (phamos/phriend/setup.py), so they
# stay hidden on Issues that are no Phriend report and have no GitLab issue. Issue starts with
# the Section Break `subject_section`, so the section swallows no standard field.
ISSUE_FIELDS = [
	{
		"fieldname": IMPLEMENTATION_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
		# the section used to show only on Phriend and GitLab issues; clear that condition
		"depends_on": "",
	},
	{
		"fieldname": "custom_team",
		"label": "Team",
		"fieldtype": "Link",
		"options": "Team",
		"insert_after": IMPLEMENTATION_SECTION,
		"description": "The team this issue belongs to. It shows in that team's Team Cockpit.",
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


def ensure_task_fields():
	ensure_module()
	create_custom_fields({"Task": [{**field, "module": MODULE} for field in TASK_FIELDS]}, update=True)


def ensure_issue_fields():
	ensure_module()
	create_custom_fields({"Issue": [{**field, "module": MODULE} for field in ISSUE_FIELDS]}, update=True)
	expand_issue_sections()


def expand_issue_sections():
	"""Every section on the Issue form open, never collapsible (#2157).

	A Property Setter for each standard Section Break that ERPNext makes collapsible, read from
	the DocFields, so a section ERPNext makes collapsible later is covered on the next migrate.
	Our own sections are not collapsible at their source (custom fields). With collapsible off,
	Frappe ignores `collapsible_depends_on` (ERPNext opens "Details" only on closed issues).
	"""
	sections = frappe.get_all(
		"DocField",
		filters={"parent": "Issue", "parenttype": "DocType", "fieldtype": "Section Break", "collapsible": 1},
		pluck="fieldname",
	)
	for fieldname in sections:
		current = frappe.db.get_value(
			"Property Setter", {"doc_type": "Issue", "field_name": fieldname, "property": "collapsible"}, "value"
		)
		if current == "0":
			continue
		# A setter that makes the section collapsible again (set by hand in Customize Form) is
		# replaced: make_property_setter inserts a new setter and deletes the old one, and returns it.
		setter = make_property_setter("Issue", fieldname, "collapsible", "0", "Check")
		frappe.db.set_value("Property Setter", setter.name, "module", MODULE)


def after_migrate():
	ensure_todo_fields()
	ensure_task_fields()
	ensure_issue_fields()


def after_install():
	"""Store the Cockpit Settings defaults on a new site (#1933).

	Patches don't run on a fresh install, and a Single stores no defaults until it is saved: every
	cockpit would start grey with no glow and "show author" off. Both patches only fill in fields
	that have no stored value, so they are safe here.
	"""
	from phamos.patches.v1_0 import move_cockpit_settings, set_cockpit_window_defaults

	move_cockpit_settings.execute()
	set_cockpit_window_defaults.execute()
