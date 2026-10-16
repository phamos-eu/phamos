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
		quotation = next((d.quotation for d in group if d.quotation), None)
		if quotation and frappe.db.get_value("Quotation", quotation, "docstatus") == 1:
			so = billing.make_sales_order_from_quotation(quotation, customer=party, submit=submit)
		else:
			event = frappe.get_doc("Marketing Content", group[0].event)
			so = billing.create_sales_order(event, group, party, submit=submit)
		orders.append(so.name)
	return {"sales_orders": orders, "skipped": skipped}


@frappe.whitelist(methods=["POST"])
def create_sales_order_from_quotation(quotation, customer=None, submit=0):
	_require("Sales Order", "create")
	so = billing.make_sales_order_from_quotation(quotation, customer=customer, submit=frappe.utils.cint(submit))
	return {"sales_order": so.name}


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
