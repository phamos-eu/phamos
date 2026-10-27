# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""One ticket order for an event, free or paid, with one or more tickets (phamos/phamos#1717).

The website order creates it with the buyer, the billing data as typed and the price the buyer confirmed. The
desk creates Customer and Sales Order from it. The Attendees are the tickets; they link to their order through
``event_ticket_order``. Sales Orders and Sales Invoices point to the order (``event_ticket_order``, shown under
Connections; phamos/phamos#1727). The order's ``status`` and ``customer`` are never set by hand: they follow the
tickets (``refresh_status``), whose ``payment_status`` ``phamos.marketing.billing`` maintains.

Desk orders (``source`` "Desk", phamos/phamos#1730) are created by hand: their price comes from a price row of
the event (rate editable), quantity and total follow their tickets, and they can be changed until the Sales
Order. Website orders are never changed in the desk.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime

from phamos.marketing.utils import join_name

STATUSES = ("Free", "Booked", "Ordered", "Invoiced", "Paid", "Credited", "Cancelled")
# Until the Sales Order a desk order can be changed (phamos/phamos#1730).
EDITABLE_STATUSES = ("Booked", "Free")
# What a person may change on a desk order; everything else follows the event, the price row and the tickets.
DESK_FIELDS = ("event", "language", "buyer_first_name", "buyer_last_name", "buyer_email", "buyer_phone",
	"contact", "customer", "billing_is_company", "billing_name", "billing_company", "billing_vat_id",
	"billing_email", "billing_address_line1", "billing_address_line2", "billing_postcode", "billing_city",
	"billing_country", "ticket_type", "ticket_rate")


class EventTicketOrder(Document):
	def validate(self):
		self.buyer_name = join_name(self.buyer_first_name, self.buyer_last_name) or self.buyer_email
		if self.source == "Desk":
			self.validate_desk_order()
		elif not self.is_new():
			self.check_unchanged(_("Website orders cannot be changed."))

	def after_insert(self):
		# The buyer's own ticket, when the buyer attends (desk orders; the website creates its tickets itself).
		if self.source != "Desk" or not self.buyer_attends:
			return
		frappe.get_doc({"doctype": "Attendee", "event": self.event, "event_ticket_order": self.name, "is_buyer": 1,
			"first_name": self.buyer_first_name, "last_name": self.buyer_last_name, "email": self.buyer_email or None,
			"phone": self.buyer_phone, "company_name": self.billing_company, "language": self.language,
			"contact": self.contact, "customer": self.customer, "ticket_type": self.ticket_type or "Free"}).insert()
		self.reload()  # quantity, total and status as the ticket left them

	def check_unchanged(self, message):
		if any(self.has_value_changed(field) for field in DESK_FIELDS):
			frappe.throw(message)

	def validate_desk_order(self):
		if self.is_new():
			self.ordered_on = self.ordered_on or now_datetime()
		else:
			if self.get_doc_before_save().status not in EDITABLE_STATUSES:
				self.check_unchanged(_("Event Ticket Order {0} has a Sales Order and can no longer be changed.").format(
					self.name))
				return
			if self.has_value_changed("event") and frappe.db.exists("Attendee", {"event_ticket_order": self.name}):
				frappe.throw(_("The event of an order with tickets cannot be changed."))
		event = frappe.get_doc("Marketing Content", self.event)
		if not event.get("ticket_item"):
			self.ticket_type, self.ticket_rate, self.item_tax_template = "Free", 0, None
			if self.is_new():
				self.status = "Free"
		else:
			self.set_desk_price(event)
			if self.is_new():
				self.status = "Booked"
		self.quantity, self.confirmed_total = desk_totals(self)

	def set_desk_price(self, event):
		"""The price row the desk chose: its rate unless one was typed, gross or net and taxes as the event sells."""
		from phamos.marketing.billing import price_ladder

		if not self.ticket_type:
			frappe.throw(_("Please choose the price of the tickets."))
		row = next((r for r in price_ladder(event) if r.title == self.ticket_type), None)
		if not row:
			frappe.throw(_("{0} is not a price of event {1}.").format(self.ticket_type, event.title or event.name))
		if not self.ticket_rate:
			self.ticket_rate = row.rate
		self.ticket_rate_includes_tax = cint(event.get("ticket_price_includes_tax"))
		self.item_tax_template = event.get("item_tax_template")


def desk_totals(order):
	"""Quantity (the tickets not cancelled) and total of a desk order, computed as for a website order."""
	from phamos.marketing import billing

	quantity = 0 if order.is_new() else frappe.db.count("Attendee",
		{"event_ticket_order": order.name, "status": ["!=", "Cancelled"]})
	if not quantity or not order.item_tax_template:
		return quantity, 0
	event = frappe.get_doc("Marketing Content", order.event)
	return quantity, billing.order_total(billing.pricing_from_order(event, order), quantity).total


@frappe.whitelist()
def ticket_prices(event):
	"""The price rows a desk order can choose from (phamos/phamos#1730). Quotas and sale windows do not apply."""
	from phamos.marketing.billing import price_ladder

	doc = frappe.get_doc("Marketing Content", event)
	doc.check_permission("read")
	if not doc.get("ticket_item"):
		return {"paid": False, "prices": []}
	return {"paid": True, "prices": [{"title": row.title, "rate": row.rate} for row in price_ladder(doc)]}


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
	"""Recompute ``status`` and ``customer`` of one Event Ticket Order from its tickets (desk orders: also
	``quantity`` and ``confirmed_total``)."""
	if not order or not frappe.db.exists("Event Ticket Order", order):
		return
	tickets = frappe.get_all("Attendee", filters={"event_ticket_order": order},
		fields=["status", "payment_status", "customer", "billing_customer", "is_buyer"],
		order_by="is_buyer desc, creation asc")
	first = lambda field: next((t[field] for t in tickets if t[field]), None)  # noqa: E731
	values = {"status": order_status(tickets)}
	customer = first("billing_customer") or first("customer")
	if customer:
		values["customer"] = customer
	doc = frappe.get_doc("Event Ticket Order", order)
	# Desk orders: quantity and total follow the tickets until the Sales Order (phamos/phamos#1730).
	if doc.source == "Desk" and doc.status in EDITABLE_STATUSES:
		if not tickets and doc.ticket_type == "Free":
			values["status"] = "Free"
		values["quantity"], values["confirmed_total"] = desk_totals(doc)
	frappe.db.set_value("Event Ticket Order", order, values, update_modified=False)


def refresh_for_attendees(names):
	"""Refresh the orders of these Attendees (after billing changed their payment status)."""
	if not names:
		return
	for order in set(frappe.get_all("Attendee", filters={"name": ["in", list(names)], "event_ticket_order": ["is", "set"]},
			pluck="event_ticket_order")):
		refresh_status(order)
