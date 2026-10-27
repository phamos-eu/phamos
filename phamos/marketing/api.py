"""Desk actions on Attendees and Event Ticket Orders (list bulk actions and form buttons). POST only,
permission-checked.

Every action checks each Attendee it changes and runs with the user's own rights on the records it creates
(phamos/phamos#1709). Rights per action, so staff roles can be checked:

| Action | Needs |
|---|---|
| ``crm_matches`` | Attendee read (that row) |
| ``link_to_crm`` | Attendee write (each row); with create: Contact create, Lead create if a Lead is made; Contact write to add links; with ``customer``: Customer read (that one) |
| ``create_customers`` | Attendee write (each row), Customer create, Contact write |
| ``create_sales_orders`` | Attendee write (each row), Sales Order create (+ submit), Customer read (the party) |
| ``order_customer_proposal`` | Event Ticket Order read (that one) |
| ``create_order_sales_orders`` | Event Ticket Order write and Attendee write (each), Sales Order create and submit; "use": Customer read (that one), Lead write if the buyer's Lead gets linked; "convert" / "new": Customer create; with billing data: Contact write, Address create, Customer write to set a missing VAT ID |
| ``create_sales_invoices`` | Attendee write (each row of those orders), Sales Invoice create (+ submit); with ``ticket_orders``: Event Ticket Order read (each) |
| ``create_opportunities`` | Attendee write (each row), Opportunity create |
| ``set_attendance`` | Attendee write (each row) |
| ``send_ticket`` | Attendee write (that row) |
"""

import json

import frappe
from frappe import _

from phamos.marketing import billing, crm, ticketing


def _names(names):
	names = json.loads(names) if isinstance(names, str) and names.startswith("[") else names
	if isinstance(names, str):
		names = [names]
	if not names:
		frappe.throw(_("Please select at least one attendee."))
	return list(dict.fromkeys(names))


def _require(doctype, ptype):
	frappe.has_permission(doctype, ptype, throw=True)


def _attendees_for(names, ptype="write"):
	"""The Attendees, each checked for ``ptype`` (a doctype-level check is not enough: User Permissions or
	sharing can allow some rows and not others)."""
	docs = [frappe.get_doc("Attendee", name) for name in _names(names)]
	for doc in docs:
		doc.check_permission(ptype)
	return docs


def _readable_customer(customer):
	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} does not exist.").format(customer))
	frappe.has_permission("Customer", "read", customer, throw=True)
	return customer


def _groups(docs):
	"""Attendees grouped by order: the Event Ticket Order, else the legacy order reference, else the Customer,
	else each on its own."""
	groups = {}
	for doc in docs:
		key = doc.event_ticket_order or doc.order_reference or (f"customer:{doc.customer}" if doc.customer else doc.name)
		groups.setdefault((doc.event, key), []).append(doc)
	return list(groups.values())


def _buyer(group):
	return next((d for d in group if d.is_buyer), group[0])


@frappe.whitelist(methods=["POST"])
def crm_matches(name):
	doc = frappe.get_doc("Attendee", name)
	doc.check_permission("read")
	found = crm.find_party(doc.email, doc.company_name)
	return {"contact": found.contact, "lead": found.lead, "customer": found.customer, "customers": found.customers,
		"confidence": found.confidence, "suggestions": found.suggestions}


@frappe.whitelist(methods=["POST"])
def link_to_crm(names, create=1, customer=None):
	docs = _attendees_for(names)
	if customer:
		_readable_customer(customer)
	results = []
	for doc in docs:
		if customer:
			result = crm.link_attendee(doc.name, create=True)
			crm.ensure_contact_links(result["contact"], [("Customer", customer)])
			doc.reload()
			doc.customer, doc.crm_status = customer, "Linked"
			doc.save()
			results.append({**result, "customer": customer})
		else:
			results.append(crm.link_attendee(doc.name, create=frappe.utils.cint(create)))
	return {"count": len(results), "results": results}


@frappe.whitelist(methods=["POST"])
def create_customers(names):
	docs = _attendees_for(names)
	_require("Customer", "create")
	done = []
	for group in _groups(docs):
		buyer = _buyer(group)
		customer = crm.ensure_customer_for_order(buyer, group)
		for doc in group:
			frappe.db.set_value("Attendee", doc.name, {"billing_customer": customer}, update_modified=False)
		frappe.db.set_value("Attendee", buyer.name, {"customer": customer, "crm_status": "Linked"})
		done.append({"customer": customer, "attendees": [d.name for d in group]})
	return {"count": len(done), "results": done}


@frappe.whitelist(methods=["POST"])
def create_sales_orders(names, customer=None, submit=0):
	docs = _attendees_for(names)
	_require("Sales Order", "create")
	submit = frappe.utils.cint(submit)
	if submit:
		_require("Sales Order", "submit")
	on_order = billing.ticket_lines([d.name for d in docs])
	skipped = [d.name for d in docs if d.name in on_order or d.payment_status == "Not Required"]
	docs = [d for d in docs if d.name not in skipped]
	orders = []
	for group in _groups(docs):
		party = customer or next((d.billing_customer or d.customer for d in group if d.billing_customer or d.customer), None)
		if not party:
			frappe.throw(_("{0}: no Customer yet. Run \"Create Customer(s)\" first or choose a Customer.").format(
				_buyer(group).full_name))
		_readable_customer(party)
		event = frappe.get_doc("Marketing Content", group[0].event)
		so = billing.create_sales_order(event, group, party, submit=submit)  # with the user's own rights
		orders.append(so.name)
	return {"sales_orders": orders, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def order_customer_proposal(name):
	"""What the "Create Sales Order" dialog proposes for an Event Ticket Order (``crm.order_customer_proposal``)."""
	order = frappe.get_doc("Event Ticket Order", name)
	order.check_permission("read")
	proposal = crm.order_customer_proposal(order)
	if proposal.customer:
		proposal.customer_name = frappe.db.get_value("Customer", proposal.customer, "customer_name")
	if proposal.lead:
		proposal.lead_name = frappe.db.get_value("Lead", proposal.lead, "lead_name")
	return proposal


@frappe.whitelist(methods=["POST"])
def create_order_sales_orders(names, mode=None, customer=None):
	"""Customer and submitted Sales Order for booked Event Ticket Orders, at the price the buyer confirmed
	(phamos/phamos#1725).

	One order (form button): ``mode`` and ``customer`` as chosen in the dialog ("use" + customer, "convert",
	"new"). Several orders (list bulk action, no ``mode``): each order takes its proposal, but only when it is
	unambiguous (``crm.order_customer_proposal``); every other order is skipped and listed. Orders that are
	not Booked are skipped too. A total that differs from the confirmed one stops the whole action (rollback).
	"""
	orders = [frappe.get_doc("Event Ticket Order", name) for name in _names(names)]
	for order in orders:
		order.check_permission("write")
	if mode and len(orders) > 1:
		frappe.throw(_("Choose the Customer for one order at a time."))
	_require("Sales Order", "create")
	_require("Sales Order", "submit")
	created, skipped = [], []
	for order in orders:
		if order.status != "Booked":
			skipped.append({"order": order.name, "reason": _("not booked ({0})").format(_(order.status))})
			continue
		order_mode, order_customer = mode, customer
		if not mode:
			proposal = crm.order_customer_proposal(order)
			if not proposal.unambiguous:
				skipped.append({"order": order.name, "reason": _("choose the Customer in the order")})
				continue
			order_mode, order_customer = proposal.action, proposal.customer
		created.append(_order_sales_order(order, order_mode, order_customer))
	return {"sales_orders": created, "skipped": skipped}


def _order_sales_order(order, mode, customer):
	if mode == "use":
		if not customer:
			frappe.throw(_("Please choose a Customer."))
		_readable_customer(customer)
	else:
		_require("Customer", "create")
	names = frappe.get_all("Attendee", filters={"event_ticket_order": order.name, "status": ["!=", "Cancelled"]},
		pluck="name", order_by="is_buyer desc, creation asc")
	on_order = billing.ticket_lines(names)
	tickets = [frappe.get_doc("Attendee", name) for name in names if name not in on_order]
	if not tickets:
		frappe.throw(_("{0} has no tickets to order.").format(order.name))
	for doc in tickets:
		doc.check_permission("write")
	customer = crm.customer_for_order(order, mode, customer)
	contact, address = crm.apply_billing_to_customer(order, customer)
	event = frappe.get_doc("Marketing Content", order.event)
	pricing = billing.pricing_from_order(event, order)
	# The buyer confirmed the total of all tickets; with tickets cancelled since, it is the same price for fewer.
	confirmed = order.confirmed_total if len(tickets) == order.quantity else billing.order_total(pricing, len(tickets)).total
	so = billing.create_sales_order(event, tickets, customer, pricing=pricing, submit=True, contact=contact,
		address=address, email=order.billing_email or order.buyer_email, lang=order.language,
		confirmed_total=confirmed, event_ticket_order=order.name)  # with the user's own rights
	return so.name


@frappe.whitelist(methods=["POST"])
def create_sales_invoices(names=None, sales_orders=None, submit=0, ticket_orders=None):
	_require("Sales Invoice", "create")
	submit = frappe.utils.cint(submit)
	if submit:
		_require("Sales Invoice", "submit")
	orders = json.loads(sales_orders) if isinstance(sales_orders, str) else (sales_orders or [])
	# Tickets that are ordered but not invoiced yet: their Sales Orders.
	uninvoiced = []
	if names:
		uninvoiced += [d.name for d in _attendees_for(names) if d.payment_status == "Ordered"]
	if ticket_orders:
		for order in _names(ticket_orders):
			frappe.has_permission("Event Ticket Order", "read", order, throw=True)
			uninvoiced += frappe.get_all("Attendee", filters={"event_ticket_order": order, "payment_status": "Ordered"},
				pluck="name")
	orders += billing.ticket_lines(uninvoiced).values()
	invoices, skipped = [], []
	for so in dict.fromkeys(orders):
		# Only event orders, and only with write on each of their attendees.
		attendees = frappe.get_all("Sales Order Item", filters={"parent": so, "attendee": ["is", "set"]},
			pluck="attendee")
		if not attendees or frappe.db.get_value("Sales Order", so, "docstatus") != 1:
			skipped.append(so)
			continue
		_attendees_for(attendees)
		invoices.append(billing.make_sales_invoice(so, submit=submit).name)
	return {"sales_invoices": invoices, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def send_ticket(name):
	"""Desk "Send Ticket": the ticket mail for this Attendee now, also above the daily limit (phamos/phamos#1704)."""
	doc = frappe.get_doc("Attendee", name)
	doc.check_permission("write")
	if not doc.email:
		frappe.throw(_("This attendee has no email address."))
	order_field = "event_ticket_order" if doc.event_ticket_order else "order_reference"
	buyer = frappe.db.get_value("Attendee", {order_field: doc.get(order_field), "is_buyer": 1},
		["first_name", "last_name"], as_dict=True) if doc.get(order_field) and not doc.is_buyer else None
	buyer_name = " ".join(filter(None, [buyer.first_name, buyer.last_name])) if buyer else None
	ticketing.send_ticket(doc.name, buyer_name=buyer_name, lang=doc.language or "de", ignore_limit=True)
	return {"sent_to": doc.email}


@frappe.whitelist(methods=["POST"])
def set_attendance(names, status):
	if status not in ("Attended", "No Show", "Registered", "Confirmed", "Cancelled"):
		frappe.throw(_("Invalid status"))
	for doc in _attendees_for(names):
		doc.status = status
		doc.save()
	return {"count": len(_names(names))}


@frappe.whitelist(methods=["POST"])
def attendee_summary(event):
	frappe.has_permission("Marketing Content", "read", event, throw=True)
	return ticketing.attendee_counts(event)


@frappe.whitelist(methods=["POST"])
def create_campaign(event):
	frappe.has_permission("Marketing Content", "write", event, throw=True)
	return crm.get_or_create_campaign(frappe.get_doc("Marketing Content", event))


@frappe.whitelist(methods=["POST"])
def create_opportunities(names):
	"""One Opportunity per attendee after the follow-up call showed real interest (none at registration:
	a ticket is a closed sale, an Opportunity a deal someone works on)."""
	docs = _attendees_for(names)
	_require("Opportunity", "create")
	created, skipped = [], []
	for att in docs:
		name = att.name
		party_type, party = ("Customer", att.customer) if att.customer else ("Lead", att.lead) if att.lead else (None, None)
		if att.opportunity or not party:
			skipped.append(name)
			continue
		event = frappe.get_doc("Marketing Content", att.event)
		opportunity = frappe.get_doc({
			"doctype": "Opportunity",
			"opportunity_from": party_type,
			"party_name": party,
			"title": _("Follow-up {0}: {1}").format(event.title, att.full_name)[:140],
			"contact_person": att.contact,
			"contact_email": att.email,
			"source": crm.ensure_lead_source(),
			"campaign": crm.get_or_create_campaign(event),
			"opportunity_owner": frappe.session.user,
			"status": "Open",
		})
		opportunity.insert()
		opportunity.add_comment("Comment", _("Created from attendee {0} of {1}.").format(att.name, event.title))
		frappe.db.set_value("Attendee", name, {"opportunity": opportunity.name, "follow_up_status": "Done"})
		created.append(opportunity.name)
	return {"opportunities": created, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def create_ticket_item(event):
	"""A non-stock service item for the event's tickets, set as its Ticket Item."""
	frappe.has_permission("Marketing Content", "write", event, throw=True)
	_require("Item", "create")
	doc = frappe.get_doc("Marketing Content", event)
	if doc.ticket_item:
		return doc.ticket_item
	group = "Services" if frappe.db.exists("Item Group", {"name": "Services", "is_group": 0}) else \
		frappe.db.get_value("Item Group", {"is_group": 0}, "name", order_by="lft asc")
	item = frappe.get_doc({"doctype": "Item", "item_code": f"TICKET-{doc.route or doc.name}"[:140].upper(),
		"item_name": _("Ticket {0}").format(doc.title)[:140], "item_group": group, "stock_uom": "Nos",
		"is_stock_item": 0, "include_item_in_manufacturing": 0, "is_sales_item": 1, "is_purchase_item": 0,
		"description": _("Ticket for {0}").format(doc.title)})
	item.insert()
	doc.db_set("ticket_item", item.name)
	return item.name
