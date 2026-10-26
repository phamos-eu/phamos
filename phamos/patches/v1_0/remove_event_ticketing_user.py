"""Remove the "Event Ticketing" service user, its role and its permission rows (phamos/phamos#1726, #1717).

Website orders no longer create Sales Orders, so nothing runs as the service user any more. In this order:
1. Leads it owns get the Lead Owner "Guest", as every website Lead since phamos/phamos#1718 (the Lead
   Assignment Rule leaves them alone).
2. The role's Custom DocPerm rows are deleted. Where the doctype's remaining Custom DocPerm rows are an
   untouched copy of its standard permissions (Item, Account, ...), they are deleted too, so the doctype
   follows ERPNext's standard permissions again; a copy someone changed is kept and printed.
3. The user is deleted with Frappe's own deletion (it removes its ToDos, shares and settings and unlinks
   Contacts). If another document still links to it, the patch prints the link and keeps the user and the
   role, so nothing is half-deleted.
4. The role is deleted.

``owner`` fields of old documents keep the email as text. Prints what it does; running it again changes nothing.
"""

import frappe
from frappe.utils import strip_html

from phamos.marketing.setup import TICKETING_DOCTYPES, TICKETING_ROLE, TICKETING_USER, custom_perms_match_standard


def execute():
	leads = frappe.get_all("Lead", filters={"lead_owner": TICKETING_USER}, pluck="name")
	for lead in leads:
		frappe.db.set_value("Lead", lead, "lead_owner", "Guest", update_modified=False)
	if leads:
		print(f"Lead Owner set to Guest on {len(leads)} Lead(s) of {TICKETING_USER}")

	doctypes = set(frappe.get_all("Custom DocPerm", filters={"role": TICKETING_ROLE}, pluck="parent"))
	for doctype in sorted(doctypes | set(TICKETING_DOCTYPES)):
		own = frappe.db.count("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE})
		frappe.db.delete("Custom DocPerm", {"parent": doctype, "role": TICKETING_ROLE})
		rest = frappe.db.count("Custom DocPerm", {"parent": doctype})
		if rest and custom_perms_match_standard(doctype):
			frappe.db.delete("Custom DocPerm", {"parent": doctype})
			print(f"{doctype}: removed {own} Event Ticketing row(s) and the untouched copy ({rest} rows)")
		elif rest and own:
			print(f"{doctype}: removed {own} Event Ticketing row(s); kept {rest} customised row(s)")
		elif own:
			print(f"{doctype}: removed {own} Event Ticketing row(s)")
		frappe.clear_cache(doctype=doctype)

	if frappe.db.exists("User", TICKETING_USER):
		frappe.db.savepoint("remove_event_ticketing_user")
		try:
			frappe.delete_doc("User", TICKETING_USER, ignore_permissions=True)
		except frappe.LinkExistsError as e:
			# Frappe names the linking document in the message log, the exception only says "disable instead".
			details = [strip_html(frappe.parse_json(m).get("message", "")) for m in frappe.local.message_log]
			frappe.db.rollback(save_point="remove_event_ticketing_user")
			frappe.clear_messages()
			print(f"{TICKETING_USER} kept, still linked: {' '.join(filter(None, details)) or strip_html(str(e))}")
			return
		print(f"User {TICKETING_USER} deleted")

	if frappe.db.exists("Role", TICKETING_ROLE):
		frappe.delete_doc("Role", TICKETING_ROLE, ignore_permissions=True)
		print(f"Role {TICKETING_ROLE} deleted")
