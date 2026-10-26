"""Tickets as ERPNext documents: prices over time, the Sales Order, the invoice and the payment status.

Prices live on the event (``Marketing Content.ticket_prices``): rows such as "Early Bird" (until a date,
for a quota) and "Regular". The first row whose window contains the order time and whose quota still
covers the order wins; a sold-out or expired row falls through to the next (``select_price``).

A website order is the customer's binding order ("Zahlungspflichtig bestellen"). It is stored as an Event
Ticket Order with the price the buyer confirmed; the desk turns it into a submitted Sales Order at that price
(phamos/phamos#1725). Every line is one ticket for one attendee, described as
"<ticket> (<price>) – <name>": ERPNext rejects the same item twice on one document unless the
descriptions differ, and the invoice shows who each ticket is for. Gross prices are entered as the line
rate with tax rows "included in print rate", so a consumer pays exactly the advertised price.

The hooks at the end keep ``Attendee.payment_status`` current. Payments reach an invoice only through
``db_set`` (outstanding amount, status), which fires ``on_change`` – not ``on_update_after_submit`` –
so ``on_sales_invoice_change`` is hooked on ``on_change``.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count
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

	Without an Item Tax Template there are no rows: summing the sales template's rates would show 26 % for a
	7 % + 19 % template. Ticket sales stay closed until the event has one (``ticketing.sale_state``,
	phamos/phamos#1710).
	"""
	if not event_doc.get("item_tax_template"):
		return []
	item_rates = {}
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


def sold_per_price(event_name, for_update=False):
	"""{price title: seats taken} for the event (cancelled attendees do not count).

	``for_update``: a locking read, which sees the latest committed rows instead of the transaction's
	snapshot. The order uses it after locking the event row (``ticketing._register``).
	"""
	attendee = frappe.qb.DocType("Attendee")
	query = (frappe.qb.from_(attendee).select(attendee.ticket_type, Count("*"))
		.where((attendee.event == event_name) & attendee.status.isin(SEAT_STATUSES)).groupby(attendee.ticket_type))
	if for_update:
		query = query.for_update()
	return {ticket_type: n for ticket_type, n in query.run()}


def _gross_net(rate, inclusive, tax_rate):
	rate = flt(rate)
	if inclusive:
		return rate, flt(rate / (1 + tax_rate / 100), 2)
	return flt(rate * (1 + tax_rate / 100), 2), rate


def price_ladder(event_doc, now=None, exclude_hold=None, for_update=False):
	"""All price rows with gross, net, remaining quota and whether they can still be sold, in table order.
	Seats other visitors hold right now (20-minute holds, ``ticketing.hold_seats``) count against the quota."""
	from phamos.marketing.ticketing import active_holds

	now = get_datetime(now or now_datetime())
	taxes = tax_rows(event_doc)
	tax_rate = sum(flt(r.tax_rate) for r in taxes)
	inclusive = cint(event_doc.get("ticket_price_includes_tax"))
	sold = sold_per_price(event_doc.name, for_update=for_update) if event_doc.get("name") else {}
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


def select_price(event_doc, qty=1, now=None, exclude_hold=None, for_update=False):
	"""The price row an order of ``qty`` tickets gets now, or None when no row can take it."""
	for row in price_ladder(event_doc, now, exclude_hold=exclude_hold, for_update=for_update):
		if row.available and (row.remaining is None or row.remaining >= qty):
			return row
	return None


def get_ticket_pricing(event_doc, qty=1, now=None, exclude_hold=None, for_update=False):
	"""Everything an order line needs, for the price row that applies now; None for free events or when
	nothing can be sold (no price row, sold out, windows over)."""
	item_code = event_doc.get("ticket_item")
	if not item_code:
		return None
	if not event_doc.get("item_tax_template"):
		frappe.throw(_("Event {0} has no Item Tax Template for its tickets.").format(event_doc.get("title") or event_doc.name))
	price = select_price(event_doc, qty, now, exclude_hold=exclude_hold, for_update=for_update)
	if not price:
		return None
	return _pricing(event_doc, price)


def pricing_for_attendee(event_doc, attendee):
	"""Desk orders: the price of the attendee's own row, at its current rate. Quotas and sale windows do not
	apply, the seat was given at registration (phamos/phamos#1711). An attendee without a matching row
	(empty, "Free" on a now paid event, a renamed or deleted row) gets the row that applies now, else the
	last one; such attendees count against no quota, so they cannot push themselves to the next row."""
	if not event_doc.get("item_tax_template"):
		frappe.throw(_("Event {0} has no Item Tax Template for its tickets.").format(event_doc.get("title") or event_doc.name))
	ladder = price_ladder(event_doc)
	if not ladder:
		frappe.throw(_("{0}: no ticket price can be found for event {1}.").format(attendee.full_name, event_doc.title))
	own = next((row for row in ladder if row.title == attendee.ticket_type), None)
	return _pricing(event_doc, own or select_price(event_doc, 1) or ladder[-1]), bool(own)


def pricing_from_order(event_doc, order):
	"""The price the buyer confirmed, from the Event Ticket Order (phamos/phamos#1725): its ticket type, rate,
	gross or net, and Item Tax Template, never the event's current price table. Taxes and item come from the
	event as for every order."""
	event = frappe._dict(event_doc.as_dict())
	event.item_tax_template = order.item_tax_template or event.item_tax_template
	event.ticket_price_includes_tax = order.ticket_rate_includes_tax
	if not event.item_tax_template:
		frappe.throw(_("Event {0} has no Item Tax Template for its tickets.").format(event.title or event.name))
	tax_rate = sum(flt(r.tax_rate) for r in tax_rows(event))
	gross, net = _gross_net(order.ticket_rate, cint(order.ticket_rate_includes_tax), tax_rate)
	return _pricing(event, frappe._dict(title=order.ticket_type, rate=flt(order.ticket_rate), gross=gross, net=net))


def _pricing(event_doc, price):
	item_code = event_doc.get("ticket_item")
	taxes = tax_rows(event_doc)
	inclusive = cint(event_doc.get("ticket_price_includes_tax"))
	item_name = frappe.db.get_value("Item", item_code, "item_name") or item_code
	return frappe._dict(item_code=item_code, item_name=item_name, price_title=price.title, rate=price.rate,
		gross=price.gross, net=price.net, inclusive=inclusive, tax_rows=taxes,
		tax_rate=sum(flt(r.tax_rate) for r in taxes), currency=company_currency(),
		item_tax_template=event_doc.get("item_tax_template"), tc_name=event_doc.get("tc_name"),
		taxes_and_charges=sales_taxes_template(event_doc),
		price_list=frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling")


def order_total(pricing, qty):
	"""{net_total, tax_total, total} of an order of ``qty`` tickets, computed as ERPNext computes the Sales Order.

	Net prices: the lines are net, and every tax row is rounded once on the order's net total, so 3 × 10.01 €
	net at 19 % is 35.74 €, not 3 × 11.91 € = 35.73 €. Gross prices (tax included): the total is qty × gross,
	which ERPNext keeps by adjusting the last tax row. The website shows this total, sends it back as the
	confirmed total, and the Sales Order must match it to the cent (phamos/phamos#1710).
	"""
	qty = cint(qty)
	if pricing.inclusive:
		total = flt(pricing.gross * qty, 2)
		net_total = flt(total / (1 + flt(pricing.tax_rate) / 100), 2)
		return frappe._dict(net_total=net_total, tax_total=flt(total - net_total, 2), total=total)
	net_total = flt(pricing.net * qty, 2)
	tax_total = flt(sum(flt(net_total * flt(row.tax_rate) / 100, 2) for row in pricing.tax_rows), 2)
	return frappe._dict(net_total=net_total, tax_total=tax_total, total=flt(net_total + tax_total, 2))


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


def _append_lines(doc, priced):
	"""One line per attendee: ``priced`` is [(attendee, pricing)]. The taxes come from the event, so they are
	the same for every pricing."""
	pricing = priced[0][1]
	for att, line_pricing in priced:
		line_rate = line_pricing.gross if line_pricing.inclusive else line_pricing.net
		doc.append("items", {
			"item_code": line_pricing.item_code,
			"qty": 1,
			"rate": line_rate,
			"price_list_rate": line_rate,
			"description": line_description(line_pricing.item_name, line_pricing.price_title, att.full_name),
			"additional_notes": "\n".join(filter(None, [att.full_name, att.email])),
			"item_tax_template": line_pricing.item_tax_template,
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
		email=None, lang=None, confirmed_total=None, ignore_permissions=False):
	"""Sales Order with one line per attendee, created in the desk.

	``pricing`` is the price the buyer confirmed (``pricing_from_order``, Event Ticket Orders). Without it
	(attendees added by hand, old orders) every attendee is billed at their own price row (``pricing_for_attendee``).
	``confirmed_total``: the total the buyer confirmed; the order is refused if ERPNext computes another one.
	``ignore_permissions``: False for desk orders, which run with the user's own rights (phamos/phamos#1709).
	Attendees get ``sales_order`` / ``sales_order_item`` / ``billing_customer`` / ``order_reference``.
	"""
	from phamos.marketing.crm import ensure_lead_source, get_or_create_campaign

	if pricing:
		priced, keeps_type = [(att, pricing) for att in attendees], {att.name: False for att in attendees}
	else:
		priced, keeps_type = [], {}
		for att in attendees:
			att_pricing, own = pricing_for_attendee(event_doc, att)
			priced.append((att, att_pricing))
			keeps_type[att.name] = own
	pricing = priced[0][1]
	so = frappe.new_doc("Sales Order")
	so.customer = customer
	so.company = default_company()
	so.order_type = "Shopping Cart"
	so.transaction_date = nowdate()
	so.delivery_date = max(getdate(event_doc.get("starts_on") or nowdate()), getdate(nowdate()))
	so.selling_price_list = pricing.price_list
	so.currency = pricing.currency
	so.ignore_pricing_rule = 1
	so.disable_rounded_total = 1  # the buyer pays exactly the confirmed total, no whole-euro rounding
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
	_append_lines(so, priced)
	so.flags.ignore_permissions = ignore_permissions
	so.insert()
	if confirmed_total is not None and abs(flt(so.grand_total) - flt(confirmed_total)) >= 0.005:
		# Must never happen once order_total matches ERPNext (e.g. the tax template was changed after the order);
		# if it does, nobody pays another amount than confirmed. Deferred, so the entry survives the rollback.
		frappe.log_error(title=_("Event order total differs from the confirmed total"),
			message=f"Event {event_doc.name}: confirmed {confirmed_total}, Sales Order {so.grand_total}",
			reference_doctype="Marketing Content", reference_name=event_doc.name, defer_insert=True)
		frappe.throw(_("Total differs from the confirmed total ({0} vs {1}): check the tax template").format(
			flt(so.grand_total, 2), flt(confirmed_total, 2)), title=_("Total differs"))
	for (att, att_pricing), row in zip(priced, so.items):
		values = {"sales_order": so.name, "sales_order_item": row.name, "billing_customer": customer,
			"order_reference": att.order_reference or so.name, "payment_status": "Ordered" if submit else "Pending"}
		if not keeps_type[att.name]:
			values["ticket_type"] = att_pricing.price_title  # an attendee's own price row is never overwritten
		frappe.db.set_value("Attendee", att.name, values, update_modified=False)
	_refresh_orders([att.name for att, _pricing in priced])
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


def payment_status_for_lines(lines):
	"""{Sales Order line: (sales_invoice, payment_status)} from the submitted invoices and credit notes of
	these order lines (one line per attendee). Lines without a submitted invoice are left out.

	Per line (phamos/phamos#1706): the latest regular invoice whose line is not fully credited is the current
	one: "Paid" when its outstanding is 0 or less, else "Invoiced". If every regular invoice of the line was
	credited, the line is "Credited" and keeps pointing at the latest original invoice, never the credit note.
	So a correction (credit note, then a new invoice) ends with the new invoice. Drafts never count.
	"""
	if not lines:
		return {}
	si, item = frappe.qb.DocType("Sales Invoice"), frappe.qb.DocType("Sales Invoice Item")
	rows = (frappe.qb.from_(item).join(si).on(item.parent == si.name)
		.select(item.so_detail, item.qty, si.name, si.is_return, si.return_against, si.outstanding_amount, si.creation)
		.where(item.so_detail.isin(list(lines)) & (si.docstatus == 1)).orderby(si.creation).run(as_dict=True))
	result = {}
	for line in lines:
		own = [r for r in rows if r.so_detail == line]
		credited = {}
		for r in own:
			if r.is_return and r.return_against:
				credited[r.return_against] = credited.get(r.return_against, 0) + flt(r.qty)
		regular = [r for r in own if not r.is_return]
		if not regular:
			continue
		current = [r for r in regular if flt(r.qty) + credited.get(r.name, 0) > 0]
		if current:
			invoice = current[-1]
			result[line] = (invoice.name, "Paid" if flt(invoice.outstanding_amount) <= 0 else "Invoiced")
		else:
			result[line] = (regular[-1].name, "Credited")
	return result


def refresh_payment_status(lines):
	"""Recompute ``sales_invoice`` and ``payment_status`` of the Attendees of these Sales Order lines."""
	lines = [line for line in dict.fromkeys(lines) if line]
	if not lines:
		return
	attendees = frappe.get_all("Attendee", filters={"sales_order_item": ["in", lines]},
		fields=["name", "sales_order_item"])
	if not attendees:
		return
	state = payment_status_for_lines({a.sales_order_item for a in attendees})
	for att in attendees:
		invoice, status = state.get(att.sales_order_item, (None, "Ordered"))
		frappe.db.set_value("Attendee", att.name, {"sales_invoice": invoice, "payment_status": status},
			update_modified=False)
	_refresh_orders([a.name for a in attendees])


# --- hooks ----------------------------------------------------------------------------------------------


def _attendees(filters):
	return frappe.get_all("Attendee", filters=filters, pluck="name")


def _set(names, values):
	for name in names:
		frappe.db.set_value("Attendee", name, values, update_modified=False)
	_refresh_orders(names)


def _refresh_orders(names):
	"""Billing writes the tickets with db.set_value (no document hooks): refresh their orders' status here."""
	from phamos.marketing.doctype.event_ticket_order.event_ticket_order import refresh_for_attendees

	refresh_for_attendees(names)



def on_sales_order_update(doc, method=None):
	"""Keep the Attendee links when a person edits the order (e.g. changes the Customer of a draft).

	Runs on every Sales Order save: one query for all lines, and nothing more for orders without
	attendees (phamos/phamos#1707)."""
	lines = [row.name for row in doc.items if row.name]
	names = _attendees({"sales_order_item": ["in", lines]}) if lines else []
	if not names:
		return
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
			# Follow-up link of a submit the user was allowed to do: not checked again on the Contact.
			ensure_contact_links(att.contact, [("Customer", doc.customer)], ignore_permissions=True)
			if not att.customer:
				# Without a Contact (companion without email) the person is not in the CRM yet.
				values = {"customer": doc.customer}
				if att.contact:
					values["crm_status"] = "Linked"
				frappe.db.set_value("Attendee", att.name, values, update_modified=False)


def on_sales_order_cancel(doc, method=None):
	names = _attendees({"sales_order": doc.name})
	for name in names:
		frappe.db.set_value("Attendee", name, {"sales_order": None, "sales_order_item": None,
			"sales_invoice": None, "payment_status": "Pending"},
			update_modified=False)
	_refresh_orders(names)


def on_sales_invoice_change(doc, method=None):
	"""Hooked on ``on_change`` only: it runs once after every save, submit and cancel, and also when a payment
	or credit note changes the invoice through ``db_set`` (which runs ``on_change`` as well)."""
	lines = [row.so_detail for row in doc.items if row.get("so_detail")]
	if doc.get("is_return") and doc.get("return_against"):
		lines += frappe.get_all("Sales Invoice Item", filters={"parent": doc.return_against}, pluck="so_detail")
	lines += frappe.get_all("Attendee", filters={"sales_invoice": doc.name}, pluck="sales_order_item")
	refresh_payment_status(lines)


def on_sales_invoice_trash(doc, method=None):
	# A draft being deleted: the attendees fall back to their other (submitted) invoices, if any.
	refresh_payment_status(frappe.get_all("Attendee", filters={"sales_invoice": doc.name}, pluck="sales_order_item"))


def on_payment_entry_change(doc, method=None):
	for ref in doc.get("references") or []:
		if ref.reference_doctype == "Sales Invoice" and _attendees({"sales_invoice": ref.reference_name}):
			on_sales_invoice_change(frappe.get_doc("Sales Invoice", ref.reference_name))


def sync_payment_status():
	"""Daily safety net for payments booked in ways that bypass the hooks."""
	refresh_payment_status(frappe.get_all("Attendee", filters={"sales_order_item": ["is", "set"],
		"payment_status": ["in", ["Ordered", "Invoiced"]]}, pluck="sales_order_item"))


def lead_before_insert(doc, method=None):
	"""ERPNext's Lead saves its auto-created Contact without ignoring permissions (lead.py link_to_contact),
	which fails for website guests. Carry the Lead's own flag over to that Contact."""
	if doc.flags.ignore_permissions and getattr(doc, "contact_doc", None):
		doc.contact_doc.flags.ignore_permissions = True

