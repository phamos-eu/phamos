"""Idempotent setup of the Marketing module (``after_migrate``).

- Lead Source "Event" for registrations.
- Role "Event Ticketing" + user ``TICKETING_USER``: website orders run as this user instead of Guest.
  Every document is inserted with ``ignore_permissions``, but ERPNext checks two things with the session
  user's own permissions while validating a Sales Order or Sales Invoice: read on the Item
  (``get_item_details`` → ``item.check_permission``) and select on the receivable Account
  (``erpnext/accounts/party.py: account_perm_check``). The role grants the read-only master data those
  paths touch and select on Account; it cannot write anything. The user has no password and never logs
  in (phamos/phamos#1180: no Administrator elevation).
"""

import frappe
from frappe.permissions import add_permission, update_permission_property

from phamos.marketing.crm import ensure_lead_source

TICKETING_ROLE = "Event Ticketing"
TICKETING_USER = "event-ticketing@phamos.invalid"
# What ERPNext reads with the session user's permissions while validating a Quotation: the item and
# its price, the party (Lead or Customer: get_lead_details / get_party_details) and, for a Customer,
# the receivable Account (account_perm_check accepts "select"). Nothing is writable.
TICKETING_READ = ("Item", "Item Price", "Price List", "UOM", "Item Tax Template", "Currency", "Customer",
	"Contact", "Address", "Company", "Customer Group", "Territory", "Terms and Conditions")
TICKETING_SELECT = ("Account",)


def after_migrate():
	ensure_lead_source()
	ensure_ticketing_user()


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
