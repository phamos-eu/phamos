# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Role of the General Management Cockpit (#1946).

The role is the only way into the cockpit (besides System Manager), and it carries the rights on
the doctypes the cockpit works with, so the role alone is enough. Users get it by hand.
"""

import frappe
from frappe.core.doctype.doctype.doctype import validate_permissions_for_doctype
from frappe.permissions import add_permission, update_permission_property

GENERAL_MANAGEMENT_ROLE = "phamos General Management"

# Doctypes the cockpit reads and writes (phamos/api/department_cockpit.py; Contract: #2148).
DOCTYPES = ("Issue", "Task", "Checklist", "Contract")
GRANTED = ("read", "write", "create", "report", "export", "print", "email", "share")
# No delete: managers close or cancel records, they don't remove them.
WITHHELD = ("delete",)


def after_migrate():
	"""Idempotent: create the role and its rights; running it again changes nothing."""
	ensure_role()
	for doctype in DOCTYPES:
		ensure_permissions(doctype)


def ensure_role():
	if frappe.db.exists("Role", GENERAL_MANAGEMENT_ROLE):
		return
	frappe.get_doc(
		{
			"doctype": "Role",
			"role_name": GENERAL_MANAGEMENT_ROLE,
			"desk_access": 1,
			"is_custom": 1,
		}
	).insert(ignore_permissions=True)


def ensure_permissions(doctype, role=GENERAL_MANAGEMENT_ROLE, granted=GRANTED, withheld=WITHHELD):
	"""Give `role` the `granted` and not the `withheld` rights on `doctype` (Custom DocPerm, permlevel 0).

	Also used for the Implementation Cockpit role (phamos/setup/implementation_cockpit.py).
	"""
	rule = {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
	if not frappe.db.exists("Custom DocPerm", rule):
		# The first custom rule copies the stock DocPerms into Custom DocPerm.
		add_permission(doctype, role, permlevel=0, ptype="read")

	current = frappe.db.get_value("Custom DocPerm", rule, [*granted, *withheld], as_dict=True)
	wanted = {**{ptype: 1 for ptype in granted}, **{ptype: 0 for ptype in withheld}}
	changed = [ptype for ptype, value in wanted.items() if (current.get(ptype) or 0) != value]
	if not changed:
		return
	for ptype in changed:
		update_permission_property(doctype, role, 0, ptype, wanted[ptype], validate=False)
	validate_permissions_for_doctype(doctype)
	frappe.clear_cache(doctype=doctype)
