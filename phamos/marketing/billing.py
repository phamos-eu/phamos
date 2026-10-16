"""Tickets as ERPNext documents: prices over time, the Sales Order, the invoice and the payment status.

Prices live on the event (``Marketing Content.ticket_prices``): rows such as "Early Bird" (until a date,
for a quota) and "Regular". The first row whose window contains the order time and whose quota still
covers the order wins; a sold-out or expired row falls through to the next (``select_price``).

A website order is the customer's binding order ("Zahlungspflichtig bestellen"), so it becomes a
submitted Sales Order right away. Every line is one ticket for one attendee, described as
"<ticket> (<price>) – <name>": ERPNext rejects the same item twice on one document unless the
descriptions differ, and the invoice shows who each ticket is for. Gross prices are entered as the line
rate with tax rows "included in print rate", so a consumer pays exactly the advertised price.

The hooks at the end keep ``Attendee.payment_status`` current. Payments reach an invoice only through
``db_set`` (outstanding amount, status), which fires ``on_change`` – not ``on_update_after_submit`` –
so ``on_sales_invoice_change`` is hooked on ``on_change``.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, nowdate

from phamos.marketing.defaults import LEAD_SOURCE, SEAT_STATUSES

# --- pricing --------------------------------------------------------------------------------------------


def default_company():
	return frappe.defaults.get_global_default("company") or frappe.db.get_single_value("Global Defaults", "default_company")


def company_currency():
	return frappe.get_cached_value("Company", default_company(), "default_currency") or "EUR"


def sales_taxes_template(event_doc):
	"""The event's Sales Taxes and Charges Template, else the company default."""
	if event_doc.get("taxes_and_charges"):
		return event_doc.taxes_and_charges
	return frappe.db.get_value("Sales Taxes and Charges Template", {"company": default_company(), "is_default": 1,
		"disabled": 0})


def tax_rows(event_doc):
	"""The tax rows of a ticket order, each with the rate that applies to the ticket.

	As ERPNext computes it: the Sales Taxes and Charges Template says which accounts apply (German chart:
	"Umsatzsteuer 7 %" and "Umsatzsteuer 19 %"), the Item Tax Template sets the rate per account (19 % on
	one, not applicable on the other). Without a sales template the Item Tax Template rows are used as
	they are (only sensible for a template with a single output-tax account).
	"""
	item_rates = {}
	if event_doc.get("item_tax_template"):
		for row in frappe.get_all("Item Tax Template Detail", filters={"parent": event_doc.item_tax_template},
				fields=["tax_type", "tax_rate", "not_applicable"]):
			item_rates[row.tax_type] = 0 if row.not_applicable else flt(row.tax_rate)
	template = sales_taxes_template(event_doc)
	rows = []
	if template:
		for row in frappe.get_all("Sales Taxes and Charges", filters={"parenttype": "Sales Taxes and Charges Template",
				"parent": template, "charge_type": "On Net Total"}, fields=["account_head", "description", "rate"],
				order_by="idx asc"):
			rate = item_rates.get(row.account_head, flt(row.rate))
			rows.append(frappe._dict(tax_type=row.account_head, description=row.description or row.account_head,
				tax_rate=rate, template_rate=flt(row.rate)))
	else:
		rows = [frappe._dict(tax_type=account, description=account, tax_rate=rate, template_rate=rate)
			for account, rate in item_rates.items() if rate]
	return rows


def sold_per_price(event_name):
	"""{price title: seats taken} for the event (cancelled attendees do not count)."""
	rows = frappe.get_all("Attendee", filters={"event": event_name, "status": ["in", SEAT_STATUSES]},
		fields=["ticket_type", "count(name) as n"], group_by="ticket_type")
	return {r.ticket_type: r.n for r in rows}


def _gross_net(rate, inclusive, tax_rate):
	rate = flt(rate)
	if inclusive:
		return rate, flt(rate / (1 + tax_rate / 100), 2)
	return flt(rate * (1 + tax_rate / 100), 2), rate


def price_ladder(event_doc, now=None, exclude_hold=None):
	"""All price rows with gross, net, remaining quota and whether they can still be sold, in table order.
	Seats other visitors hold right now (20-minute holds, ``ticketing.hold_seats``) count against the quota."""
	from phamos.marketing.ticketing import active_holds

	now = get_datetime(now or now_datetime())
	taxes = tax_rows(event_doc)
	tax_rate = sum(flt(r.tax_rate) for r in taxes)
	inclusive = cint(event_doc.get("ticket_price_includes_tax"))
	sold = sold_per_price(event_doc.name) if event_doc.get("name") else {}
	for hold in (active_holds(event_doc.name, exclude=exclude_hold) if event_doc.get("name") else {}).values():
		if hold.get("price_title"):
			sold[hold["price_title"]] = cint(sold.get(hold["price_title"])) + cint(hold.get("qty"))
	ladder = []
	for row in event_doc.get("ticket_prices") or []:
		gross, net = _gross_net(row.rate, inclusive, tax_rate)
		quota = cint(row.quota)
		remaining = max(0, quota - cint(sold.get(row.title))) if quota else None
		started = not row.valid_from or now >= get_datetime(row.valid_from)
		ended = bool(row.valid_until) and now > get_datetime(row.valid_until)
		ladder.append(frappe._dict(title=row.title, rate=flt(row.rate), gross=gross, net=net, quota=quota or None,
			remaining=remaining, valid_from=row.valid_from, valid_until=row.valid_until,
			available=started and not ended and remaining != 0, upcoming=not started, ended=ended))
	return ladder


def select_price(event_doc, qty=1, now=None, exclude_hold=None):
	"""The price row an order of ``qty`` tickets gets now, or None when no row can take it."""
	for row in price_ladder(event_doc, now, exclude_hold=exclude_hold):
		if row.available and (row.remaining is None or row.remaining >= qty):
			return row
	return None


def get_ticket_pricing(event_doc, qty=1, now=None, exclude_hold=None):
	"""Everything an order line needs, for the price row that applies now; None for free events or when
	nothing can be sold (no price row, sold out, windows over)."""
	item_code = event_doc.get("ticket_item")
	if not item_code:
		return None
	price = select_price(event_doc, qty, now, exclude_hold=exclude_hold)
	if not price:
		return None
	taxes = tax_rows(event_doc)
	inclusive = cint(event_doc.get("ticket_price_includes_tax"))
	item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
	return frappe._dict(item_code=item_code, item_name=item_name, price_title=price.title, rate=price.rate,
		gross=price.gross, net=price.net, inclusive=inclusive, tax_rows=taxes,
		tax_rate=sum(flt(r.tax_rate) for r in taxes), currency=company_currency(),
		item_tax_template=event_doc.get("item_tax_template"), tc_name=event_doc.get("tc_name"),
		taxes_and_charges=sales_taxes_template(event_doc),
		price_list=frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling")


def price_summary(event_doc):
	"""Text for the desk field "Price Overview": one line per price row."""
	from frappe.utils import fmt_money

	lines = []
	currency = company_currency()
	for row in price_ladder(event_doc):
		window = " – ".join(filter(None, [frappe.utils.format_datetime(row.valid_from, "dd.MM.yyyy HH:mm") if row.valid_from else "",
			frappe.utils.format_datetime(row.valid_until, "dd.MM.yyyy HH:mm") if row.valid_until else ""]))
		quota = _("{0} of {1} left").format(row.remaining, row.quota) if row.quota else _("no quota")
		lines.append(_("{0}: {1} incl. VAT (net {2}); {3}{4}").format(row.title, fmt_money(row.gross, currency=currency),
			fmt_money(row.net, currency=currency), quota, f"; {window}" if window else ""))
	return "\n".join(lines)


def line_description(item_name, price_title, full_name):
	return f"{item_name} ({price_title}) – {full_name}" if price_title else f"{item_name} – {full_name}"


def _append_lines(doc, pricing, attendees):
	line_rate = pricing.gross if pricing.inclusive else pricing.net
	for att in attendees:
		doc.append("items", {
			"item_code": pricing.item_code,
			"qty": 1,
			"rate": line_rate,
			"price_list_rate": line_rate,
			"description": line_description(pricing.item_name, pricing.price_title, att.full_name),
			"additional_notes": "\n".join(filter(None, [att.full_name, att.email])),
			"item_tax_template": pricing.item_tax_template,
			"delivery_date": doc.get("delivery_date"),
		})
	cost_center = frappe.get_cached_value("Company", doc.company, "cost_center")
	doc.taxes_and_charges = pricing.taxes_and_charges
	for row in pricing.tax_rows:
		# The row keeps the template's rate; ERPNext applies the Item Tax Template rate per line (item_tax_rate).
		doc.append("taxes", {"charge_type": "On Net Total", "account_head": row.tax_type,
			"rate": row.template_rate if pricing.taxes_and_charges else row.tax_rate,
			"description": row.description, "cost_center": cost_center,
			"included_in_print_rate": 1 if pricing.inclusive else 0})


# --- documents ------------------------------------------------------------------------------------------


def create_sales_order(event_doc, attendees, customer, *, pricing=None, submit=False, contact=None, address=None,
		email=None, lang=None):
	"""Sales Order with one line per attendee. Website orders (as the service user) and desk orders use it.

	``pricing`` is the price the buyer saw and confirmed; without it the price that applies now is used.
	Attendees get ``sales_order`` / ``sales_order_item`` / ``billing_customer`` / ``order_reference``.
	"""
	from phamos.marketing.crm import ensure_lead_source, get_or_create_campaign

	pricing = pricing or get_ticket_pricing(event_doc, len(attendees))
	if not pricing:
		frappe.throw(_("No ticket price can be sold for event {0} right now.").format(event_doc.title))
	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = default_company()
	so.order_type = "Shopping Cart"
	so.transaction_date = nowdate()
	so.delivery_date = max(getdate(event_doc.get("starts_on") or nowdate()), getdate(nowdate()))
	so.selling_price_list = pricing.price_list
	so.currency = pricing.currency
	so.ignore_pricing_rule = 1
	so.campaign = get_or_create_campaign(event_doc)
	so.source = ensure_lead_source(LEAD_SOURCE)
	so.project = event_doc.get("project")
	so.contact_person = contact
	so.contact_email = email
	so.customer_address = address
	if lang:
		so.language = lang
	if pricing.tc_name:
		so.tc_name = pricing.tc_name
	_append_lines(so, pricing, attendees)
	so.flags.ignore_permissions = True
	so.insert()
	for att, row in zip(attendees, so.items):
		frappe.db.set_value("Attendee", att.name, {"sales_order": so.name, "sales_order_item": row.name,
			"billing_customer": customer, "order_reference": att.order_reference or so.name, "ticket_type": pricing.price_title,
			"payment_status": "Ordered" if submit else "Pending"}, update_modified=False)
	if submit:
		so.submit()
	return so


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



def on_sales_order_update(doc, method=None):
	"""Keep the Attendee links when a person edits the order (e.g. changes the Customer of a draft)."""
	for row in doc.items:
		names = _attendees({"sales_order_item": row.name})
		values = {"sales_order": doc.name, "billing_customer": doc.customer}
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
				# Without a Contact (companion without email) the person is not in the CRM yet.
				values = {"customer": doc.customer}
				if att.contact:
					values["crm_status"] = "Linked"
				frappe.db.set_value("Attendee", att.name, values, update_modified=False)


def on_sales_order_cancel(doc, method=None):
	for att in frappe.get_all("Attendee", filters={"sales_order": doc.name}, fields=["name"]):
		frappe.db.set_value("Attendee", att.name, {"sales_order": None, "sales_order_item": None,
			"sales_invoice": None, "payment_status": "Pending"},
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
