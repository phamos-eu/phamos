"""Tickets as ERPNext documents: Quotation → Sales Order → Sales Invoice, and the payment status.

Website orders become a submitted Quotation (to the buyer's Customer when we know it, else to their
Lead). A phamos person confirms with ERPNext's standard "Create → Sales Order": ERPNext then creates
the Customer from the Lead (type Company or Individual) and moves its Contacts and Address over.
Imported orders (the July 2026 backfill) get a Sales Order directly.

Every line is one ticket for one attendee, described as "<ticket> – <name>" (ERPNext rejects the same
item twice on one document unless the descriptions differ). Attendees are linked through the standard
row references: ``quotation_item`` on Sales Order items, ``so_detail`` on Sales Invoice items.

The hooks at the end keep ``Attendee.payment_status`` current. Payments reach an invoice only through
``db_set`` (outstanding amount, status), which fires ``on_change`` – not ``on_update_after_submit`` –
so ``on_sales_invoice_change`` is hooked on ``on_change``.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from phamos.marketing.defaults import LEAD_SOURCE, QUOTATION_VALID_DAYS

# --- pricing --------------------------------------------------------------------------------------------


def default_company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")


def price_list_for(event_doc):
	return (event_doc.get("selling_price_list")
		or frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling")


def get_ticket_pricing(event_doc):
	"""Net rate, currency and tax rows of the event's ticket item, or None without a ticket item."""
	item_code = event_doc.get("ticket_item")
	if not item_code:
		return None
	item = frappe.db.get_value("Item", item_code, ["item_name", "description", "standard_rate"], as_dict=True)
	if not item:
		return None
	price_list = price_list_for(event_doc)
	price = frappe.db.get_value("Item Price", {"item_code": item_code, "price_list": price_list, "selling": 1},
		["price_list_rate", "currency"], as_dict=True, order_by="valid_from desc")
	currency = (price.currency if price else None) or frappe.db.get_value("Price List", price_list, "currency") \
		or frappe.db.get_value("Company", default_company(), "default_currency") or "EUR"
	rate = flt(price.price_list_rate if price else item.standard_rate)
	tax_rows = []
	if event_doc.get("item_tax_template"):
		tax_rows = frappe.get_all("Item Tax Template Detail", filters={"parent": event_doc.item_tax_template,
			"tax_rate": [">", 0]}, fields=["tax_type", "tax_rate"], order_by="idx asc")
	tax_rate = sum(flt(r.tax_rate) for r in tax_rows)
	return frappe._dict(item_code=item_code, item_name=item.item_name, rate=rate, currency=currency,
		price_list=price_list, item_tax_template=event_doc.get("item_tax_template"), tax_rows=tax_rows,
		tax_rate=tax_rate, gross=flt(rate * (1 + tax_rate / 100), 2), tc_name=event_doc.get("tc_name"))


def line_description(item_name, full_name):
	return f"{item_name} – {full_name}"


def _append_lines(doc, pricing, attendees):
	for att in attendees:
		doc.append("items", {
			"item_code": pricing.item_code,
			"qty": 1,
			"rate": pricing.rate,
			"price_list_rate": pricing.rate,
			"description": line_description(pricing.item_name, att.full_name),
			"additional_notes": f"{att.full_name}\n{att.email}",
			"item_tax_template": pricing.item_tax_template,
		})
	cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
	for row in pricing.tax_rows:
		doc.append("taxes", {"charge_type": "On Net Total", "account_head": row.tax_type, "rate": row.tax_rate,
			"description": row.tax_type, "cost_center": cost_center})


def _header(doc, event_doc, pricing):
	from phamos.marketing.crm import ensure_lead_source, get_or_create_campaign

	doc.company = default_company()
	doc.order_type = "Shopping Cart"
	doc.transaction_date = nowdate()
	doc.selling_price_list = pricing.price_list
	doc.currency = pricing.currency
	doc.ignore_pricing_rule = 1
	doc.campaign = get_or_create_campaign(event_doc)
	doc.source = ensure_lead_source(LEAD_SOURCE)
	if pricing.tc_name:
		doc.tc_name = pricing.tc_name


def quotation_valid_till(event_doc):
	end = event_doc.get("ends_on") or event_doc.get("starts_on")
	candidates = [getdate(add_days(nowdate(), QUOTATION_VALID_DAYS))]
	if end:
		candidates.append(getdate(end))
	return max(candidates)


# --- documents ------------------------------------------------------------------------------------------


def create_quotation(event_doc, attendees, party_type, party, buyer_email=None, submit=True):
	"""Submitted Quotation for a website order; runs as Guest, so permissions are ignored explicitly.

	``attendees``: saved Attendee docs. They get ``quotation`` / ``quotation_item`` / "Quoted".
	A Quotation (unlike a Sales Order) never reads the party's receivable Account, so no elevated user
	is needed (phamos/phamos#1180).
	"""
	pricing = get_ticket_pricing(event_doc)
	if not pricing:
		frappe.throw(_("No ticket item is configured for this event."))
	qtn = frappe.new_doc("Quotation")
	qtn.quotation_to = party_type
	qtn.party_name = party
	_header(qtn, event_doc, pricing)
	qtn.valid_till = quotation_valid_till(event_doc)
	qtn.contact_email = buyer_email
	qtn.title = _("Tickets: {0}").format(event_doc.title)[:140]
	_append_lines(qtn, pricing, attendees)
	qtn.flags.ignore_permissions = True
	qtn.insert()
	if submit:
		qtn.submit()
	for att, row in zip(attendees, qtn.items):
		frappe.db.set_value("Attendee", att.name, {"quotation": qtn.name, "quotation_item": row.name,
			"order_reference": qtn.name, "payment_status": "Quoted"}, update_modified=False)
	return qtn


def create_sales_order(event_doc, attendees, customer, submit=False, po_no=None):
	"""Sales Order straight from Attendees (desk and backfill; runs with the desk user's permissions)."""
	pricing = get_ticket_pricing(event_doc)
	if not pricing:
		frappe.throw(_("No ticket item is configured for event {0}.").format(event_doc.name))
	so = frappe.new_doc("Sales Order")
	so.customer = customer
	_header(so, event_doc, pricing)
	so.delivery_date = getdate(event_doc.get("starts_on") or nowdate())
	so.project = event_doc.get("project")
	reference = attendees[0].order_reference or attendees[0].name
	so.po_no = po_no or _("Tickets {0} – {1}").format(event_doc.title, reference)[:140]
	so.po_date = nowdate()
	_append_lines(so, pricing, attendees)
	for row in so.items:
		row.delivery_date = so.delivery_date
	so.insert()
	for att, row in zip(attendees, so.items):
		frappe.db.set_value("Attendee", att.name, {"sales_order": so.name, "sales_order_item": row.name,
			"billing_customer": customer, "order_reference": att.order_reference or reference,
			"payment_status": "Ordered" if submit else att.payment_status}, update_modified=False)
	if submit:
		so.submit()
	return so


def make_sales_order_from_quotation(quotation, customer=None, submit=False):
	"""ERPNext's "Create → Sales Order".

	``customer``: an existing Customer a person matched the order to. The Quotation is moved from the Lead
	to that Customer first (and the Lead's Contacts linked to it), so ERPNext does not create a second
	Customer from the Lead.
	"""
	from erpnext.selling.doctype.quotation.quotation import make_sales_order

	if customer:
		assign_quotation_to_customer(quotation, customer)
	so = make_sales_order(quotation)
	so.delivery_date = so.delivery_date or nowdate()
	for row in so.items:
		row.delivery_date = row.delivery_date or so.delivery_date
	so.insert()
	if submit:
		so.submit()
	return so


def assign_quotation_to_customer(quotation, customer):
	from phamos.marketing.crm import ensure_contact_links

	qtn = frappe.db.get_value("Quotation", quotation, ["quotation_to", "party_name"], as_dict=True)
	if qtn.quotation_to == "Customer" and qtn.party_name == customer:
		return
	if qtn.quotation_to == "Lead":
		lead = qtn.party_name
		for contact in frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "link_doctype": "Lead",
				"link_name": lead}, pluck="parent"):
			ensure_contact_links(contact, [("Customer", customer)])
		for address in frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": "Lead",
				"link_name": lead}, pluck="parent"):
			doc = frappe.get_doc("Address", address)
			if not doc.has_link("Customer", customer):
				doc.append("links", {"link_doctype": "Customer", "link_name": customer})
				doc.save(ignore_permissions=True)
		frappe.db.set_value("Lead", lead, {"customer": customer, "status": "Converted"})
	frappe.db.set_value("Quotation", quotation, {"quotation_to": "Customer", "party_name": customer,
		"customer_name": frappe.db.get_value("Customer", customer, "customer_name")})
	frappe.get_doc("Quotation", quotation).add_comment("Info",
		_("Assigned to the existing Customer {0} before creating the Sales Order.").format(customer))
	_set(_attendees({"quotation": quotation}), {"customer": customer, "crm_status": "Linked"})


def make_sales_invoice(sales_order, submit=False):
	from erpnext.selling.doctype.sales_order.sales_order import make_sales_invoice as _make

	si = _make(sales_order)
	si.insert()
	if submit:
		si.submit()
	return si


def payment_status_for_invoice(si):
	if si.docstatus != 1:
		return "Ordered"
	if si.status == "Credit Note Issued":
		return "Cancelled"
	if si.status == "Paid" or flt(si.outstanding_amount) <= 0:
		return "Paid"
	return "Invoiced"


# --- hooks ----------------------------------------------------------------------------------------------


def _attendees(filters):
	return frappe.get_all("Attendee", filters=filters, pluck="name")


def _set(names, values):
	for name in names:
		frappe.db.set_value("Attendee", name, values, update_modified=False)


def on_quotation_cancel(doc, method=None):
	names = _attendees({"quotation": doc.name, "sales_order": ["in", ["", None]]})
	if method == "on_trash":
		_set(names, {"quotation": None, "quotation_item": None, "payment_status": "Pending"})
	else:
		_set(names, {"payment_status": "Cancelled"})


def on_sales_order_update(doc, method=None):
	"""Link the Attendees of the order's Quotation lines (also for drafts)."""
	for row in doc.items:
		if row.get("quotation_item"):
			names = _attendees({"quotation_item": row.quotation_item})
			values = {"sales_order": doc.name, "sales_order_item": row.name, "billing_customer": doc.customer}
			if doc.docstatus == 1:
				values["payment_status"] = "Ordered"
			_set(names, values)


def on_sales_order_submit(doc, method=None):
	on_sales_order_update(doc, method)
	names = _attendees({"sales_order": doc.name})
	_set(names, {"payment_status": "Ordered", "billing_customer": doc.customer})
	customer_type = frappe.db.get_value("Customer", doc.customer, "customer_type")
	from phamos.marketing.crm import ensure_contact_links

	for att in frappe.get_all("Attendee", filters={"name": ["in", names or [""]]},
			fields=["name", "contact", "is_buyer", "customer"]):
		# A company pays for everybody it sends; a private buyer pays only for themself as a customer.
		if customer_type == "Company" or att.is_buyer or len(names) == 1:
			ensure_contact_links(att.contact, [("Customer", doc.customer)])
			if not att.customer:
				frappe.db.set_value("Attendee", att.name, {"customer": doc.customer, "crm_status": "Linked"},
					update_modified=False)


def on_sales_order_cancel(doc, method=None):
	for att in frappe.get_all("Attendee", filters={"sales_order": doc.name}, fields=["name", "quotation"]):
		frappe.db.set_value("Attendee", att.name, {"sales_order": None, "sales_order_item": None,
			"sales_invoice": None, "payment_status": "Quoted" if att.quotation else "Pending"},
			update_modified=False)


def on_sales_invoice_change(doc, method=None):
	so_rows = [row.so_detail for row in doc.items if row.get("so_detail")]
	names = _attendees({"sales_order_item": ["in", so_rows]}) if so_rows else []
	names = list(dict.fromkeys(names + _attendees({"sales_invoice": doc.name})))
	if not names:
		return
	if doc.docstatus == 2:
		_set(names, {"sales_invoice": None, "payment_status": "Ordered"})
	else:
		_set(names, {"sales_invoice": doc.name, "payment_status": payment_status_for_invoice(doc)})


def on_sales_invoice_trash(doc, method=None):
	_set(_attendees({"sales_invoice": doc.name}), {"sales_invoice": None, "payment_status": "Ordered"})


def on_payment_entry_change(doc, method=None):
	for ref in doc.get("references") or []:
		if ref.reference_doctype == "Sales Invoice" and _attendees({"sales_invoice": ref.reference_name}):
			on_sales_invoice_change(frappe.get_doc("Sales Invoice", ref.reference_name))


def sync_payment_status():
	"""Daily safety net for payments booked in ways that bypass the hooks."""
	for si in frappe.get_all("Attendee", filters={"sales_invoice": ["is", "set"],
			"payment_status": ["not in", ["Paid", "Cancelled"]]}, pluck="sales_invoice", distinct=True):
		on_sales_invoice_change(frappe.get_doc("Sales Invoice", si))


def lead_before_insert(doc, method=None):
	"""ERPNext's Lead saves its auto-created Contact without ignoring permissions (lead.py link_to_contact),
	which fails for website guests. Carry the Lead's own flag over to that Contact."""
	if doc.flags.ignore_permissions and getattr(doc, "contact_doc", None):
		doc.contact_doc.flags.ignore_permissions = True
