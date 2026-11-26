# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Schema Phriend adds to Issue, created in code (not fixtures), and the default settings.

Called from `after_migrate`. Idempotent.

Placement follows the convention in phamos/cockpits/setup.py: the section "Implementation Specific" at the
very top of the form. Issue starts with a Section Break (subject_section), which closes the section. The
section is shown on Issues that Phriend created (phriend_type is set) and on Issues with a GitLab issue
(gitlab_issue_url, the first one, is set); the Phriend-only fields inside it stay hidden on the others.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Phriend"
REPORT_DOCTYPE = "Issue"
IMPLEMENTATION_SECTION = "custom_implementation_specific"
ONLY_PHRIEND = "eval:doc.phriend_type"
PHRIEND_OR_GITLAB = "eval:doc.phriend_type || doc.gitlab_issue_url"

_FIELDS = [
	{
		"fieldname": IMPLEMENTATION_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
		"depends_on": PHRIEND_OR_GITLAB,
	},
	{
		"fieldname": "phriend_reported_by",
		"label": "Reported By",
		"fieldtype": "Link",
		"options": "User",
		"read_only": 1,
		"in_standard_filter": 1,
		"insert_after": IMPLEMENTATION_SECTION,
	},
	{
		"fieldname": "phriend_reported_by_name",
		"label": "Reporter Name",
		"fieldtype": "Data",
		"read_only": 1,
		"fetch_from": "phriend_reported_by.full_name",
		"insert_after": "phriend_reported_by",
	},
	{
		"fieldname": "phriend_source_system",
		"label": "Reported On System",
		"fieldtype": "Data",
		"read_only": 1,
		"in_standard_filter": 1,
		"description": "Set when the report came from another system (a develop or test system with this one as its target)",
		"insert_after": "phriend_reported_by_name",
	},
	{
		# The Implementation the report is about (#1671): set by Phriend, shown in the Implementation Cockpit.
		"fieldname": "custom_implementation",
		"label": "Implementation",
		"fieldtype": "Link",
		"options": "Implementation",
		"in_standard_filter": 1,
		"insert_after": "phriend_source_system",
	},
	{
		"fieldname": "phriend_type",
		"label": "Report Type",
		"fieldtype": "Select",
		"options": "\nBug\nImprovement\nQuestion\nOther",
		"in_standard_filter": 1,
		"depends_on": ONLY_PHRIEND,
		"insert_after": "custom_implementation",
	},
	{
		"fieldname": "phriend_comment",
		"label": "Reporter Comment",
		"fieldtype": "Small Text",
		"depends_on": ONLY_PHRIEND,
		"insert_after": "phriend_type",
	},
	# the first GitLab issue; the block below lists all of them (GitLab Issue.issue)
	{
		"fieldname": "gitlab_issue_url",
		"label": "GitLab Issue",
		"fieldtype": "Data",
		"options": "URL",
		"read_only": 1,
		"hidden": 1,
		"no_copy": 1,
		"insert_after": "phriend_comment",
	},
	{
		"fieldname": "phriend_gitlab_issues",
		"label": "GitLab Issues",
		"fieldtype": "HTML",
		"insert_after": "gitlab_issue_url",
	},
	{"fieldname": "phriend_col", "fieldtype": "Column Break", "insert_after": "phriend_gitlab_issues"},
	{
		"fieldname": "phriend_screenshot_preview",
		"label": "Screenshot Preview",
		"fieldtype": "HTML",
		"insert_after": "phriend_col",
	},
	{
		"fieldname": "phriend_screenshot",
		"label": "Screenshot",
		"fieldtype": "Attach Image",
		"depends_on": ONLY_PHRIEND,
		"insert_after": "phriend_screenshot_preview",
	},
	# where it happened + raw context, open like every Issue section (#2157)
	{
		"fieldname": "phriend_context_section",
		"label": "Phriend: Where It Happened",
		"fieldtype": "Section Break",
		"collapsible": 0,
		"depends_on": ONLY_PHRIEND,
		"insert_after": "phriend_screenshot",
	},
	{
		"fieldname": "phriend_ref_doctype",
		"label": "Reported DocType",
		"fieldtype": "Link",
		"options": "DocType",
		"read_only": 1,
		"in_standard_filter": 1,
		"insert_after": "phriend_context_section",
	},
	{
		"fieldname": "phriend_ref_docname",
		"label": "Reported Document",
		"fieldtype": "Dynamic Link",
		"options": "phriend_ref_doctype",
		"read_only": 1,
		"insert_after": "phriend_ref_doctype",
	},
	{
		"fieldname": "phriend_route",
		"label": "Route",
		"fieldtype": "Data",
		"read_only": 1,
		"insert_after": "phriend_ref_docname",
	},
	{
		"fieldname": "phriend_page_url",
		"label": "Page URL",
		"fieldtype": "Small Text",
		"read_only": 1,
		"insert_after": "phriend_route",
	},
	{
		"fieldname": "phriend_source_url",
		"label": "Reported On System URL",
		"fieldtype": "Data",
		"options": "URL",
		"read_only": 1,
		"insert_after": "phriend_page_url",
	},
	{"fieldname": "phriend_context_col", "fieldtype": "Column Break", "insert_after": "phriend_source_url"},
	{
		"fieldname": "phriend_context",
		"label": "Captured Context",
		"fieldtype": "Code",
		"options": "JSON",
		"read_only": 1,
		"insert_after": "phriend_context_col",
	},
]
ISSUE_FIELDS = [{**field, "module": MODULE} for field in _FIELDS]

DEFAULT_SETTINGS = {
	"enabled": 1,
	"allowed_role": "System Manager",
	"gitlab_url": "https://git.phamos.eu",
	"gitlab_project": "phamos/phamos",  # internal assistant: issues go to the phamos project
	"gitlab_labels": "phriend",
}


REMOTE_ROLE = "Phriend Remote"


def after_migrate():
	ensure_issue_fields()
	ensure_default_settings()
	ensure_remote_role()


def ensure_remote_role():
	"""The role of the API user a develop or test system sends its reports with (phamos.phriend.remote)."""
	if not frappe.db.exists("Role", REMOTE_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": REMOTE_ROLE, "desk_access": 0}).insert(ignore_permissions=True)


def ensure_issue_fields():
	create_custom_fields({REPORT_DOCTYPE: ISSUE_FIELDS}, update=True)


def ensure_default_settings():
	"""Fill the settings once, on the first migrate; later changes in the form are kept."""
	ensure_default_shortcut()
	ensure_default_features()
	if frappe.db.get_single_value("Phriend Settings", "gitlab_project"):
		return
	frappe.db.set_single_value("Phriend Settings", DEFAULT_SETTINGS)


def ensure_default_shortcut():
	"""Mod+P on sites that had Phriend before the shortcut field existed (#1900).

	A new field on a saved Single reads empty, and empty means "no shortcut" here, so the
	default from the JSON never arrives. Set it once, when the field has no row yet; an empty
	value saved later in the form (shortcut switched off) is kept.
	"""
	has_row = frappe.db.sql(
		"select 1 from `tabSingles` where doctype='Phriend Settings' and field='shortcut'"
	)
	if not has_row:
		frappe.db.set_single_value("Phriend Settings", "shortcut", "Mod+P")


# Feature switches that start on (#2009): they keep what Phriend already did. New features of
# the companion (#2008) start off and are not listed here.
FEATURES_ON_BY_DEFAULT = ("reactions",)
# Numbers whose 0 would mean something else than "not set yet" (#2011: 0 bubbles = Phriend never
# speaks by itself).
FEATURE_VALUES_BY_DEFAULT = {
	"bubbles_per_day": 1,
	# #2012: which events are red warnings, and who gets the system-wide ones
	"warn_ai_run_failed": 1,
	"warn_email_failed": 1,
	"warn_gitlab_sync_failed": 1,
	"warning_role": "System Manager",
	# #2014: the second rating question, after this many weeks in daily use
	"battle_tested_weeks": 6,
}


def ensure_default_features():
	"""Fill the values listed above on sites that saved Phriend Settings before the field
	existed: a new Check or Int on a saved Single reads 0, not its JSON default. Only when the
	field has no row yet; a value changed later in the form is kept."""
	defaults = {field: 1 for field in FEATURES_ON_BY_DEFAULT} | FEATURE_VALUES_BY_DEFAULT
	for field, value in defaults.items():
		has_row = frappe.db.sql(
			"select 1 from `tabSingles` where doctype='Phriend Settings' and field=%s", field
		)
		if not has_row:
			frappe.db.set_single_value("Phriend Settings", field, value)
