# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Role of the Implementation Cockpit for phamos staff (#1671), following #1946.

Internal users need this role (or System Manager) to open the cockpit; customers get in through
their Implementation Stakeholder rows instead. The role reads Implementations, which is what the
cockpit's scope uses (phamos/api/implementation_cockpit.py). Users get it by hand.
"""

import frappe

from phamos.setup.general_management import ensure_permissions as _ensure_permissions

IMPLEMENTATION_ROLE = "phamos Implementation"

# Issue: the cockpit lists the reports of an Implementation and shows their screenshots (private files).
# Implementation Feature: what is built for an implementation (#1968), shown in the cockpit.
# Implementation Release: release planning and its realistic check (#1986).
DOCTYPES = ("Implementation", "Issue", "Implementation Feature", "Implementation Release")
GRANTED = ("read", "report", "print")
# The cockpit shows Implementations; changes are made in Desk by the people who may make them.
WITHHELD = ("write", "create", "delete")


def after_migrate():
	"""Idempotent: create the role and its rights; running it again changes nothing."""
	if not frappe.db.exists("Role", IMPLEMENTATION_ROLE):
		frappe.get_doc(
			{"doctype": "Role", "role_name": IMPLEMENTATION_ROLE, "desk_access": 1, "is_custom": 1}
		).insert(ignore_permissions=True)
	for doctype in DOCTYPES:
		_ensure_permissions(doctype, role=IMPLEMENTATION_ROLE, granted=GRANTED, withheld=WITHHELD)
