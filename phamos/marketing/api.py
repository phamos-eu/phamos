"""Desk actions on Attendees (list bulk actions and form buttons). POST only, permission-checked."""

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


def _groups(docs):
	"""Attendees grouped by order: the order reference, else the Customer, else each on its own."""
	groups = {}
	for doc in docs:
		key = doc.order_reference or (f"customer:{doc.customer}" if doc.customer else doc.name)
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
	_require("Attendee", "write")
	results = []
	for name in _names(names):
		if customer:
			result = crm.link_attendee(name, create=True)
			crm.ensure_contact_links(result["contact"], [("Customer", customer)])
			frappe.db.set_value("Attendee", name, {"customer": customer, "crm_status": "Linked"})
			results.append({**result, "customer": customer})
		else:
			results.append(crm.link_attendee(name, create=frappe.utils.cint(create)))
	return {"count": len(results), "results": results}


@frappe.whitelist(methods=["POST"])
def create_customers(names):
	_require("Attendee", "write")
	_require("Customer", "create")
	done = []
	for group in _groups([frappe.get_doc("Attendee", n) for n in _names(names)]):
		buyer = _buyer(group)
		customer = crm.ensure_customer_for_order(buyer, group)
		for doc in group:
			frappe.db.set_value("Attendee", doc.name, {"billing_customer": customer}, update_modified=False)
		frappe.db.set_value("Attendee", buyer.name, {"customer": customer, "crm_status": "Linked"})
		done.append({"customer": customer, "attendees": [d.name for d in group]})
	return {"count": len(done), "results": done}


@frappe.whitelist(methods=["POST"])
def create_sales_orders(names, customer=None, submit=0):
	_require("Attendee", "write")
	_require("Sales Order", "create")
	submit = frappe.utils.cint(submit)
	if submit:
		_require("Sales Order", "submit")
	docs = [frappe.get_doc("Attendee", n) for n in _names(names)]
	skipped = [d.name for d in docs if d.sales_order or d.payment_status == "Not Required"]
	docs = [d for d in docs if d.name not in skipped]
	orders = []
	for group in _groups(docs):
		party = customer or next((d.billing_customer or d.customer for d in group if d.billing_customer or d.customer), None)
		if not party:
			frappe.throw(_("{0}: no Customer yet. Run \"Create Customer(s)\" first or choose a Customer.").format(
				_buyer(group).full_name))
		event = frappe.get_doc("Marketing Content", group[0].event)
		so = billing.create_sales_order(event, group, party, submit=submit)
		orders.append(so.name)
	return {"sales_orders": orders, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def create_sales_invoices(names=None, sales_orders=None, submit=0):
	_require("Sales Invoice", "create")
	submit = frappe.utils.cint(submit)
	if submit:
		_require("Sales Invoice", "submit")
	orders = json.loads(sales_orders) if isinstance(sales_orders, str) else (sales_orders or [])
	if names:
		orders += frappe.get_all("Attendee", filters={"name": ["in", _names(names)], "sales_order": ["is", "set"],
			"sales_invoice": ["in", ["", None]]}, pluck="sales_order", distinct=True)
	invoices, skipped = [], []
	for so in dict.fromkeys(orders):
		if frappe.db.get_value("Sales Order", so, "docstatus") != 1:
			skipped.append(so)
			continue
		invoices.append(billing.make_sales_invoice(so, submit=submit).name)
	return {"sales_invoices": invoices, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def send_ticket(name):
	"""Desk "Send Ticket": the ticket mail for this Attendee now, also above the daily limit (phamos/phamos#1704)."""
	doc = frappe.get_doc("Attendee", name)
	doc.check_permission("write")
	if not doc.email:
		frappe.throw(_("This attendee has no email address."))
	buyer = frappe.db.get_value("Attendee", {"order_reference": doc.order_reference, "is_buyer": 1},
		["first_name", "last_name"], as_dict=True) if doc.order_reference and not doc.is_buyer else None
	buyer_name = " ".join(filter(None, [buyer.first_name, buyer.last_name])) if buyer else None
	ticketing.send_ticket(doc.name, buyer_name=buyer_name, lang=doc.language or "de", ignore_limit=True)
	return {"sent_to": doc.email}


@frappe.whitelist(methods=["POST"])
def set_attendance(names, status):
	_require("Attendee", "write")
	if status not in ("Attended", "No Show", "Registered", "Confirmed", "Cancelled"):
		frappe.throw(_("Invalid status"))
	for name in _names(names):
		doc = frappe.get_doc("Attendee", name)
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
	_require("Attendee", "write")
	_require("Opportunity", "create")
	created, skipped = [], []
	for name in _names(names):
		att = frappe.get_doc("Attendee", name)
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
