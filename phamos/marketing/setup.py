"""Idempotent setup of the Marketing module (``after_migrate``): the Lead Source "Event" for registrations and the
fields that tie sales documents to their tickets (``SALES_DOCUMENT_FIELDS``).

Until phamos/phamos#1717 website orders created Sales Orders as a service user, "event-ticketing@phamos.invalid"
with the role "Event Ticketing" (read on Item, select on Account: ERPNext checks both with the session user's
own rights while validating a Sales Order). Website orders now only store an Event Ticket Order; the desk
creates the Sales Order with the staff member's rights. The names below stay for the patches that remove the
user, the role and the permission copies its rights left behind (``remove_unneeded_ticketing_permissions``,
``remove_event_ticketing_user``).
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

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


# The sales documents point to the ticket order and to the ticket of each line, not the other way round
# (phamos/phamos#1727). Same fieldnames on order and invoice, and not no_copy: ERPNext's mapper copies them from
# Sales Order to Sales Invoice and from an invoice to its credit note. Connections on Event Ticket Order and
# Attendee read them.
#
# Placement follows the convention in phamos/cockpits/setup.py: the section "Implementation Specific" at the
# very top. Sales Order and Sales Invoice already have it (fixture ``custom_phamos``, first by its field_order
# property setter); the item tables get their own, closed by an unlabelled Section Break, because they start
# with a plain field that the section would otherwise swallow. No depends_on: Frappe hides an empty
# read-only field anyway.
IMPLEMENTATION_SECTION = "custom_implementation_specific"
_ORDER_FIELD = {
	"fieldname": "event_ticket_order", "fieldtype": "Link", "label": "Event Ticket Order",
	"options": "Event Ticket Order", "insert_after": "custom_implementation", "read_only": 1, "search_index": 1,
	"depends_on": "", "module": "Marketing",
	"description": "The ticket order from the website this document was created from. Set automatically.",
}
_ITEM_FIELDS = [
	{"fieldname": IMPLEMENTATION_SECTION, "fieldtype": "Section Break", "label": "Implementation Specific",
		"insert_after": "", "collapsible": 0, "module": "Marketing"},
	{"fieldname": "attendee", "fieldtype": "Link", "label": "Attendee", "options": "Attendee",
		"insert_after": IMPLEMENTATION_SECTION, "read_only": 1, "search_index": 1, "depends_on": "", "module": "Marketing",
		"description": "The ticket holder this line is billed for. Set automatically."},
	{"fieldname": f"{IMPLEMENTATION_SECTION}_end", "fieldtype": "Section Break", "insert_after": "attendee",
		"module": "Marketing"},
]
SALES_DOCUMENT_FIELDS = {
	"Sales Order": [_ORDER_FIELD], "Sales Invoice": [_ORDER_FIELD],
	"Sales Order Item": _ITEM_FIELDS, "Sales Invoice Item": _ITEM_FIELDS,
}


def after_migrate():
	ensure_lead_source()
	ensure_sales_document_fields()


def ensure_sales_document_fields():
	create_custom_fields(SALES_DOCUMENT_FIELDS, update=True)


def _perm_rows(doctype, table, exclude_role=None):
	rows = frappe.get_all(table, filters={"parent": doctype}, fields=list(PERM_COLUMNS))
	return {tuple(row[column] or 0 for column in PERM_COLUMNS) for row in rows if row.role != exclude_role}


def custom_perms_match_standard(doctype):
	"""True when the doctype's Custom DocPerm rows (without the ticketing role) are an untouched copy of its
	standard DocPerm rows, i.e. nobody changed them in Role Permission Manager. Granting a role a right copies
	the standard permissions into Custom DocPerm (Frappe's ``setup_custom_perms``); such a copy no longer
	follows ERPNext's permission updates."""
	return _perm_rows(doctype, "Custom DocPerm", exclude_role=TICKETING_ROLE) == _perm_rows(doctype, "DocPerm")
