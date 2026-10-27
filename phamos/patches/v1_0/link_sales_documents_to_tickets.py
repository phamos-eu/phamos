"""Move the links between tickets and sales documents onto the sales documents (phamos/phamos#1727).

Until then each Attendee stored its Sales Order line (``sales_order_item``) and the Event Ticket Order copied
the first ticket's Sales Order and invoice. Now the lines point to the Attendee and the documents to the Event
Ticket Order (``phamos.marketing.setup.SALES_DOCUMENT_FIELDS``). For every Attendee with an old line:
- ``attendee`` on that Sales Order Item and on every Sales Invoice Item billed from it (credit notes included);
- ``event_ticket_order`` on that Sales Order and those invoices, when the Attendee belongs to an order.

The removed fields leave the doctypes, but Frappe keeps their database columns: they are read here directly.
Values already set are kept. Prints what it does; running it again changes nothing.
"""

import frappe

from phamos.marketing.setup import ensure_sales_document_fields


def execute():
	ensure_sales_document_fields()  # migrate creates them only after the patches
	if not frappe.db.has_column("Attendee", "sales_order_item"):
		return
	rows = frappe.db.sql("""select name, sales_order_item, event_ticket_order from `tabAttendee`
		where ifnull(sales_order_item, '') != ''""", as_dict=True)
	lines = invoice_lines = documents = 0
	for row in rows:
		order_item = frappe.db.get_value("Sales Order Item", row.sales_order_item, ["parent", "attendee"], as_dict=True)
		if not order_item:
			continue
		if not order_item.attendee:
			frappe.db.set_value("Sales Order Item", row.sales_order_item, "attendee", row.name, update_modified=False)
			lines += 1
		invoice_items = frappe.get_all("Sales Invoice Item", filters={"so_detail": row.sales_order_item},
			fields=["name", "parent", "attendee"])
		for item in invoice_items:
			if not item.attendee:
				frappe.db.set_value("Sales Invoice Item", item.name, "attendee", row.name, update_modified=False)
				invoice_lines += 1
		if not row.event_ticket_order:
			continue
		for doctype, name in [("Sales Order", order_item.parent)] + [("Sales Invoice", i.parent) for i in invoice_items]:
			if not frappe.db.get_value(doctype, name, "event_ticket_order"):
				frappe.db.set_value(doctype, name, "event_ticket_order", row.event_ticket_order, update_modified=False)
				documents += 1
	if lines or invoice_lines or documents:
		print(f"Linked {lines} Sales Order line(s) and {invoice_lines} Sales Invoice line(s) to their Attendee, "
			f"{documents} document(s) to their Event Ticket Order")
