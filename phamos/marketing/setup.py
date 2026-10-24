"""Idempotent setup of the Marketing module (``after_migrate``).

- Lead Source "Event" for registrations.
- Role "Event Ticketing" + user ``TICKETING_USER``: website orders run as this user instead of Guest.
  Every document is inserted with ``ignore_permissions``, but ERPNext checks two things with the session
  user's own permissions while validating a Sales Order or Sales Invoice: read on the Item
  (``get_item_details`` → ``item.check_permission``) and select on the receivable Account
  (``erpnext/accounts/party.py: account_perm_check``). The role grants exactly these two rights; it cannot
  write anything. The user has no password and never logs in (phamos/phamos#1180: no Administrator
  elevation).

Granting a role a right copies the doctype's standard permissions into Custom DocPerm (Frappe's
``setup_custom_perms``); from then on the doctype ignores permission changes that ERPNext updates ship. So
the role is kept to these two doctypes, tested by real orders (phamos/phamos#1708), and ``after_migrate``
reports in the Error Log when ERPNext's standard permissions of one of them no longer match the copy.
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

from phamos.marketing.crm import ensure_lead_source

TICKETING_ROLE = "Event Ticketing"
TICKETING_USER = "event-ticketing@phamos.invalid"
# What ERPNext checks with the session user's own rights during a website order (phamos/phamos#1708, found
# by removing one right at a time and placing paid and free orders):
# - Item read: erpnext/stock/get_item_details.py, get_item_details → item.check_permission()
# - Account select: erpnext/accounts/party.py, get_party_account → account_perm_check
TICKETING_READ = ("Item",)
TICKETING_SELECT = ("Account",)
# Granted before #1708; patches/v1_0/remove_unneeded_ticketing_permissions.py takes them back.
FORMER_TICKETING_DOCTYPES = ("Item Price", "Price List", "UOM", "Item Tax Template", "Currency", "Customer",
	"Contact", "Address", "Company", "Customer Group", "Territory", "Terms and Conditions", "Lead")
PERM_COLUMNS = ("role", "permlevel", "if_owner", "select", "read", "write", "create", "delete", "submit", "cancel",
	"amend", "report", "export", "import", "share", "print", "email")


def after_migrate():
	ensure_lead_source()
	ensure_ticketing_user()
	report_permission_drift()


def _perm_rows(doctype, table, exclude_role=None):
	rows = frappe.get_all(table, filters={"parent": doctype}, fields=list(PERM_COLUMNS))
	return {tuple(row[column] or 0 for column in PERM_COLUMNS) for row in rows if row.role != exclude_role}


def custom_perms_match_standard(doctype):
	"""True when the doctype's Custom DocPerm rows (without the ticketing role) are an untouched copy of its
	standard DocPerm rows, i.e. nobody changed them in Role Permission Manager."""
	return _perm_rows(doctype, "Custom DocPerm", exclude_role=TICKETING_ROLE) == _perm_rows(doctype, "DocPerm")


def report_permission_drift():
	"""Item and Account use a copy of their standard permissions because the ticketing role has a right on
	them. When an ERPNext update changes the standard permissions, the copy does not follow: say so."""
	for doctype in TICKETING_READ + TICKETING_SELECT:
		if frappe.db.exists("Custom DocPerm", {"parent": doctype}) and not custom_perms_match_standard(doctype):
			frappe.log_error(title=f"Permissions of {doctype}: this site uses a copy",
				message=f"ERPNext's standard permissions for {doctype} differ from this site's Custom DocPerm rows "
				f"(copied when the role Event Ticketing got its right). Check {doctype} in Role Permission Manager.",
				reference_doctype="DocType", reference_name=doctype)


def ensure_ticketing_user():
	if not frappe.db.exists("Role", TICKETING_ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": TICKETING_ROLE, "desk_access": 0, "is_custom": 1}).insert(
			ignore_permissions=True)
	for doctype in TICKETING_READ:
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE, "permlevel": 0}):
			add_permission(doctype, TICKETING_ROLE, permlevel=0, ptype="read")
		update_permission_property(doctype, TICKETING_ROLE, 0, "read", 1, validate=False)
	for doctype in TICKETING_SELECT:
		if not frappe.db.exists("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE, "permlevel": 0}):
			add_permission(doctype, TICKETING_ROLE, permlevel=0, ptype="select")
		update_permission_property(doctype, TICKETING_ROLE, 0, "select", 1, validate=False)
		update_permission_property(doctype, TICKETING_ROLE, 0, "read", 0, validate=False)
	# Buyers get no Lead any more (round 2): the role does not need to read Leads.
	if frappe.db.exists("Custom DocPerm", {"parent": "Lead", "role": TICKETING_ROLE}):
		frappe.db.delete("Custom DocPerm", {"parent": "Lead", "role": TICKETING_ROLE})
		frappe.clear_cache(doctype="Lead")
	if not frappe.db.exists("User", TICKETING_USER):
		user = frappe.get_doc({
			"doctype": "User", "email": TICKETING_USER, "first_name": "Event Ticketing", "user_type": "Website User",
			"send_welcome_email": 0, "enabled": 1, "roles": [{"role": TICKETING_ROLE}],
		})
		user.flags.no_welcome_mail = True
		user.insert(ignore_permissions=True)
	elif not frappe.db.exists("Has Role", {"parent": TICKETING_USER, "role": TICKETING_ROLE}):
		frappe.get_doc("User", TICKETING_USER).add_roles(TICKETING_ROLE)
