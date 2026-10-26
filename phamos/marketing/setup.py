"""Idempotent setup of the Marketing module (``after_migrate``): the Lead Source "Event" for registrations.

Until phamos/phamos#1717 website orders created Sales Orders as a service user, "event-ticketing@phamos.invalid"
with the role "Event Ticketing" (read on Item, select on Account: ERPNext checks both with the session user's
own rights while validating a Sales Order). Website orders now only store an Event Ticket Order; the desk
creates the Sales Order with the staff member's rights. The names below stay for the patches that remove the
user, the role and the permission copies its rights left behind (``remove_unneeded_ticketing_permissions``,
``remove_event_ticketing_user``).
"""

import frappe

from phamos.marketing.crm import ensure_lead_source

TICKETING_ROLE = "Event Ticketing"
TICKETING_USER = "event-ticketing@phamos.invalid"
# The role's last rights (phamos/phamos#1708).
TICKETING_DOCTYPES = ("Item", "Account")
# Granted before #1708; patches/v1_0/remove_unneeded_ticketing_permissions.py takes them back.
FORMER_TICKETING_DOCTYPES = ("Item Price", "Price List", "UOM", "Item Tax Template", "Currency", "Customer",
	"Contact", "Address", "Company", "Customer Group", "Territory", "Terms and Conditions", "Lead")
PERM_COLUMNS = ("role", "permlevel", "if_owner", "select", "read", "write", "create", "delete", "submit", "cancel",
	"amend", "report", "export", "import", "share", "print", "email")


def after_migrate():
	ensure_lead_source()


def _perm_rows(doctype, table, exclude_role=None):
	rows = frappe.get_all(table, filters={"parent": doctype}, fields=list(PERM_COLUMNS))
	return {tuple(row[column] or 0 for column in PERM_COLUMNS) for row in rows if row.role != exclude_role}


def custom_perms_match_standard(doctype):
	"""True when the doctype's Custom DocPerm rows (without the ticketing role) are an untouched copy of its
	standard DocPerm rows, i.e. nobody changed them in Role Permission Manager. Granting a role a right copies
	the standard permissions into Custom DocPerm (Frappe's ``setup_custom_perms``); such a copy no longer
	follows ERPNext's permission updates."""
	return _perm_rows(doctype, "Custom DocPerm", exclude_role=TICKETING_ROLE) == _perm_rows(doctype, "DocPerm")
