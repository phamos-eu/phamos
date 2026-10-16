"""Ticket prices move from the Item Price to the event (Ticket Prices table, early bird ready).

Events with a ticket item and no price rows get one row "Regular" with the selling Item Price of their
ticket item. Item Prices are net, so these events get "Prices include VAT" unticked. Attendees left in
the retired payment status "Quoted" (website orders before the direct Sales Order) go back to Pending.
"""

import frappe


def execute():
	for event in frappe.get_all("Marketing Content", filters={"ticket_item": ["is", "set"]}, fields=["name", "ticket_item"]):
		if frappe.db.exists("Marketing Event Ticket Price", {"parenttype": "Marketing Content", "parent": event.name}):
			continue
		rate = frappe.db.get_value("Item Price", {"item_code": event.ticket_item, "selling": 1}, "price_list_rate",
			order_by="valid_from desc") or frappe.db.get_value("Item", event.ticket_item, "standard_rate")
		if not rate:
			continue
		frappe.get_doc({
			"doctype": "Marketing Event Ticket Price", "parent": event.name, "parenttype": "Marketing Content",
			"parentfield": "ticket_prices", "idx": 1, "title": "Regular", "rate": rate, "quota": 0,
		}).db_insert()
		frappe.db.set_value("Marketing Content", event.name, "ticket_price_includes_tax", 0, update_modified=False)
	frappe.db.sql("update `tabAttendee` set payment_status = 'Pending' where payment_status = 'Quoted'")
