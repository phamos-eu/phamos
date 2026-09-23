# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Setup helpers for Ops Inbox (role, Issue permissions, Issue Types)."""

import frappe
from frappe.permissions import add_permission, update_permission_property

OPS_USER_ROLE = "Ops User"
INTERNAL_ISSUE_TYPES = ("Onboarding", "Process", "Internal")


def ensure_ops_inbox_setup():
	"""Idempotent setup called from after_migrate / after_install."""
	_ensure_role()
	_ensure_issue_permissions()
	_ensure_issue_types()
	_ensure_issue_department_field()


def _ensure_issue_department_field():
	"""Link Department on Issue for I Own My Work (stock Issue has Project only)."""
	if frappe.db.exists("Custom Field", {"dt": "Issue", "fieldname": "custom_department"}):
		return
	frappe.get_doc(
		{
			"doctype": "Custom Field",
			"dt": "Issue",
			"module": "Phamos",
			"label": "Department",
			"fieldname": "custom_department",
			"fieldtype": "Link",
			"options": "Department",
			"insert_after": "project",
			"in_standard_filter": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_role():
	if frappe.db.exists("Role", OPS_USER_ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": OPS_USER_ROLE,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)


def _ensure_issue_permissions():
	"""Give Ops User create/read/write on Issue (no delete)."""
	if not frappe.db.exists(
		"Custom DocPerm",
		{"parent": "Issue", "role": OPS_USER_ROLE, "permlevel": 0, "if_owner": 0},
	) and not frappe.db.exists(
		"DocPerm",
		{"parent": "Issue", "role": OPS_USER_ROLE, "permlevel": 0},
	):
		# First custom rule for Issue copies stock DocPerms into Custom DocPerm
		add_permission("Issue", OPS_USER_ROLE, permlevel=0, ptype="read")

	for ptype in ("read", "write", "create", "report", "export", "share", "print", "email"):
		update_permission_property("Issue", OPS_USER_ROLE, 0, ptype, 1, validate=False)

	update_permission_property("Issue", OPS_USER_ROLE, 0, "delete", 0, validate=True)


def _ensure_issue_types():
	for name in INTERNAL_ISSUE_TYPES:
		if frappe.db.exists("Issue Type", name):
			continue
		doc = frappe.new_doc("Issue Type")
		doc.name = name
		doc.description = f"Internal ops category: {name}"
		doc.insert(ignore_permissions=True)
