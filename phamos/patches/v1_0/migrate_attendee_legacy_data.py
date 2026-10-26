"""Fill the new Attendee fields for the rows that came from Marketing Event Registration.

- first / last name from the full name, role Guest, source Website, CRM status Unlinked
- order reference from the legacy draft ticket Sales Orders (``po_no`` "Ticket purchase for <event> ..."),
  matched by event and email from the item's ``additional_notes`` ("name\\nemail"), else from the
  registration note "Sales Order: SO-..."; such rows are marked Pending (a draft order is not an order yet)

Idempotent: only rows without a first name are touched.
"""

import frappe

from phamos.marketing.utils import normalize_email, split_name

LEGACY_PO_PREFIX = "Ticket purchase for "


def execute():
	rows = frappe.get_all("Attendee", filters={"first_name": ["in", ["", None]]},
		fields=["name", "event", "full_name", "email", "notes", "role"])
	if not rows:
		return

	orders = _legacy_order_lines()
	for row in rows:
		first, last = split_name(row.full_name)
		email = normalize_email(row.email, throw=False) or (row.email or "").strip().lower()
		values = {
			"first_name": first or email.split("@")[0],
			"last_name": last,
			"email": email,
			"role": row.role or "Guest",
			"source": "Website",  # the column default (Manual) was filled in by the model sync
			"crm_status": "Unlinked",
		}
		order = orders.get((row.event, email))
		if not order and row.notes and "Sales Order:" in row.notes:
			order = {"sales_order": row.notes.split("Sales Order:", 1)[1].strip().split()[0], "first": False}
		if order:
			values["order_reference"] = order["sales_order"]
			values["is_buyer"] = 1 if order["first"] else 0
			values["payment_status"] = "Pending"
		frappe.db.set_value("Attendee", row.name, values, update_modified=False)


def _legacy_order_lines():
	"""{(event, email): {"sales_order", "first"}} from the legacy draft ticket orders."""
	result = {}
	orders = frappe.get_all("Sales Order", filters={"po_no": ["like", f"{LEGACY_PO_PREFIX}%"], "docstatus": ["<", 2]},
		fields=["name", "po_no"])
	for so in orders:
		event = _event_from_po(so.po_no)
		items = frappe.get_all("Sales Order Item", filters={"parent": so.name}, fields=["additional_notes"], order_by="idx")
		for idx, item in enumerate(items):
			lines = (item.additional_notes or "").splitlines()
			email = normalize_email(lines[-1], throw=False) if lines else ""
			if event and email:
				result.setdefault((event, email), {"sales_order": so.name, "first": idx == 0})
	return result


def _event_from_po(po_no):
	"""The event name from "Ticket purchase for <event> YYYY-MM-DD HH:MM:SS" (older rows lack the time)."""
	rest = po_no[len(LEGACY_PO_PREFIX):]
	parts = rest.rsplit(" ", 2)
	candidates = [rest]
	if len(parts) == 3:
		candidates.insert(0, parts[0])
	for name in candidates:
		if frappe.db.exists("Marketing Content", name):
			return name
	return None
