# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Schema Phriend adds to Issue, created in code (not fixtures), and the default settings.

Called from `after_migrate`. Idempotent.

Placement follows the convention in phamos/cockpits/setup.py: the section "Implementation Specific" at the
very top of the form. Issue starts with a Section Break (subject_section), which closes the section. The
section is shown only on Issues that Phriend created (phriend_type is set).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Phriend"
REPORT_DOCTYPE = "Issue"
IMPLEMENTATION_SECTION = "custom_implementation_specific"
ONLY_PHRIEND = "eval:doc.phriend_type"

_FIELDS = [
	{
		"fieldname": IMPLEMENTATION_SECTION,
		"label": "Implementation Specific",
		"fieldtype": "Section Break",
		"insert_after": "",
		"collapsible": 0,
		"depends_on": ONLY_PHRIEND,
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
		"fieldname": "phriend_type",
		"label": "Report Type",
		"fieldtype": "Select",
		"options": "\nBug\nIdea\nQuestion",
		"in_standard_filter": 1,
		"insert_after": "phriend_reported_by_name",
	},
	{
		"fieldname": "phriend_comment",
		"label": "Reporter Comment",
		"fieldtype": "Small Text",
		"insert_after": "phriend_type",
	},
	{
		"fieldname": "gitlab_issue_url",
		"label": "GitLab Issue",
		"fieldtype": "Data",
		"options": "URL",
		"read_only": 1,
		"no_copy": 1,
		"insert_after": "phriend_comment",
	},
	{"fieldname": "phriend_col", "fieldtype": "Column Break", "insert_after": "gitlab_issue_url"},
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
		"insert_after": "phriend_screenshot_preview",
	},
	# where it happened + raw context, collapsed
	{
		"fieldname": "phriend_context_section",
		"label": "Phriend: Where It Happened",
		"fieldtype": "Section Break",
		"collapsible": 1,
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
	{"fieldname": "phriend_context_col", "fieldtype": "Column Break", "insert_after": "phriend_page_url"},
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


def after_migrate():
	ensure_issue_fields()
	ensure_default_settings()


def ensure_issue_fields():
	create_custom_fields({REPORT_DOCTYPE: ISSUE_FIELDS}, update=True)


def ensure_default_settings():
	"""Fill the settings once, on the first migrate; later changes in the form are kept."""
	if frappe.db.get_single_value("Phriend Settings", "gitlab_project"):
		return
	frappe.db.set_single_value("Phriend Settings", DEFAULT_SETTINGS)
