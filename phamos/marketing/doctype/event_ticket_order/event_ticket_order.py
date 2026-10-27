# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""One ticket order for an event, free or paid, with one or more tickets (phamos/phamos#1717).

The website order creates it with the buyer, the billing data as typed and the price the buyer confirmed. The
desk creates Customer and Sales Order from it. The Attendees are the tickets; they link to their order through
``ticket_order``. Sales Orders and Sales Invoices point to the order (``event_ticket_order``, shown under
Connections; phamos/phamos#1727). The order's ``status`` and ``customer`` are never set by hand: they follow the
tickets (``refresh_status``), whose ``payment_status`` ``phamos.marketing.billing`` maintains.
"""

import frappe
from frappe.model.document import Document

from phamos.marketing.utils import join_name

STATUSES = ("Free", "Booked", "Ordered", "Invoiced", "Paid", "Credited", "Cancelled")


class EventTicketOrder(Document):
	def validate(self):
		self.buyer_name = join_name(self.buyer_first_name, self.buyer_last_name) or self.buyer_email


def order_status(tickets):
	"""The order status from its tickets ({status, payment_status}); see the table in phamos/phamos#1723.

	Cancelled tickets only count when all are cancelled; credited ones are ignored for "Paid" as long as one
	ticket is paid."""
	if not tickets:
		return "Booked"
	if all(t.status == "Cancelled" for t in tickets):
		return "Cancelled"
	payments = [t.payment_status for t in tickets if t.status != "Cancelled"]
	if all(p == "Not Required" for p in payments):
		return "Free"
	if all(p == "Credited" for p in payments):
		return "Credited"
	if all(p in ("Paid", "Credited") for p in payments):
		return "Paid"
	if "Invoiced" in payments or "Paid" in payments:
		return "Invoiced"
	if "Ordered" in payments:
		return "Ordered"
	return "Booked"


def refresh_status(order):
	"""Recompute ``status`` and ``customer`` of one Event Ticket Order from its tickets."""
	if not order or not frappe.db.exists("Event Ticket Order", order):
		return
	tickets = frappe.get_all("Attendee", filters={"ticket_order": order},
		fields=["status", "payment_status", "customer", "billing_customer", "is_buyer"],
		order_by="is_buyer desc, creation asc")
	first = lambda field: next((t[field] for t in tickets if t[field]), None)  # noqa: E731
	values = {"status": order_status(tickets)}
	customer = first("billing_customer") or first("customer")
	if customer:
		values["customer"] = customer
	frappe.db.set_value("Event Ticket Order", order, values, update_modified=False)


def refresh_for_attendees(names):
	"""Refresh the orders of these Attendees (after billing changed their payment status)."""
	if not names:
		return
	for order in set(frappe.get_all("Attendee", filters={"name": ["in", list(names)], "ticket_order": ["is", "set"]},
			pluck="ticket_order")):
		refresh_status(order)
