"""Ticket sale and registration for one event: what is on offer, and the order itself.

``register_attendees`` is the single server-side entry for website orders. It validates everything the
browser could have skipped, re-calculates the price the buyer confirmed, links buyer and ticket holders to
the CRM like the contact form (``crm.match_or_create_lead``) and stores one Event Ticket Order with one
Attendee per ticket. Customer and Sales Order are created in the desk (phamos/phamos#1717). It runs in the
visitor's own session (Guest or a logged-in portal user) and inserts with ``ignore_permissions``; there is no
service user (phamos/phamos#1726). It never commits: the request commits on success and rolls back on any
error.
"""

import hashlib
import hmac
import re
import time

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime, nowdate
from frappe.utils.password import get_encryption_key

from phamos.marketing import billing, crm
from phamos.marketing.defaults import MAX_ATTENDEES_PER_ORDER, SEAT_STATUSES
from phamos.marketing.utils import normalize_email, split_name

OPEN_EVENT_STATUSES = ("Upcoming", "Ongoing")


# --- 20-minute holds: seats (and their price) reserved while a visitor fills in the order -------------

HOLD_MINUTES = 20


def _holds_key(event):
	return f"event_holds:{event}"


def active_holds(event, exclude=None):
	"""{hold id: {qty, price_title, expires}} of unexpired holds; expired ones are removed on the way."""
	now = time.time()
	holds = {}
	try:
		raw = frappe.cache.hgetall(_holds_key(event))
	except Exception:
		return holds
	for key, hold in raw.items():
		key = key.decode() if isinstance(key, bytes) else key
		if hold.get("expires", 0) < now:
			frappe.cache.hdel(_holds_key(event), key)
		elif key != exclude:
			holds[key] = hold
	return holds


def held_seats(event, exclude=None, price_title=None):
	return sum(cint(h.get("qty")) for h in active_holds(event, exclude).values()
		if price_title is None or h.get("price_title") == price_title)


def release_hold(event, hold_id):
	if hold_id:
		frappe.cache.hdel(_holds_key(event), hold_id)


def _hold_client():
	"""Who holds: a hash of the visitor's IP address (kept 20 minutes in Redis, never the address itself).
	None outside a web request (desk, tests, jobs)."""
	ip = getattr(frappe.local, "request_ip", None)
	if not ip:
		return None
	return hashlib.sha256(f"{frappe.local.site}|{ip}".encode()).hexdigest()[:16]


def _limit_client_holds(event_doc, hold_id, qty, client):
	"""One visitor holds at most one order's worth of seats (the event's tickets per order). A hold costs
	nothing and its id is chosen by the browser, so without this one script could keep the whole event
	"sold out". A new hold pushes out the same visitor's oldest ones; two colleagues behind one office
	router still each get a hold as long as they stay within one order's worth together, and the order
	itself re-checks the seats either way."""
	if not client:
		return
	limit = cint(event_doc.get("max_attendees_per_order")) or MAX_ATTENDEES_PER_ORDER
	own = sorted(((key, h) for key, h in active_holds(event_doc.name, exclude=hold_id).items()
		if h.get("client") == client), key=lambda kh: kh[1].get("expires", 0))
	held = sum(cint(h.get("qty")) for _key, h in own)
	while own and held + qty > limit:
		key, h = own.pop(0)
		release_hold(event_doc.name, key)
		held -= cint(h.get("qty"))


def hold_seats(event_doc, hold_id, qty):
	"""Reserve ``qty`` seats (and the price that applies to them) for 20 minutes; renewed on every call.

	Returns {ok, expires (ms since epoch), minutes, price_title, gross, total, net_total, tax_total, spots_left}
	or {ok: False, reason}. ``total`` is what an order of ``qty`` tickets costs (``billing.order_total``).
	"""
	qty = max(1, cint(qty))
	client = _hold_client()
	_limit_client_holds(event_doc, hold_id, qty, client)
	is_open, reason = sale_state(event_doc, exclude_hold=hold_id)
	if not is_open:
		release_hold(event_doc.name, hold_id)
		return {"ok": False, "reason": reason}
	capacity = cint(event_doc.max_attendees)
	taken = seats_taken(event_doc.name, exclude_hold=hold_id)
	if capacity and taken + qty > capacity:
		return {"ok": False, "reason": "sold_out", "spots_left": max(0, capacity - taken)}
	pricing = billing.get_ticket_pricing(event_doc, qty, exclude_hold=hold_id) if event_doc.get("ticket_item") else None
	if event_doc.get("ticket_item") and not pricing:
		return {"ok": False, "reason": "sold_out"}
	expires = time.time() + HOLD_MINUTES * 60
	frappe.cache.hset(_holds_key(event_doc.name), hold_id, {"qty": qty, "expires": expires,
		"price_title": pricing.price_title if pricing else None, "client": client})
	totals = billing.order_total(pricing, qty) if pricing else frappe._dict(net_total=0, tax_total=0, total=0)
	return {"ok": True, "expires": int(expires * 1000), "minutes": HOLD_MINUTES,
		"price_title": pricing.price_title if pricing else None, "gross": pricing.gross if pricing else 0,
		"qty": qty, "total": totals.total, "net_total": totals.net_total, "tax_total": totals.tax_total,
		"spots_left": max(0, capacity - taken - qty) if capacity else None}


def booked_seats(event, for_update=False):
	"""Seats of registered attendees (no holds): what the page may show as "booked".

	``for_update``: a locking read, which sees the latest committed rows instead of the transaction's
	snapshot. The order uses it after locking the event row (``_register``).
	"""
	attendee = frappe.qb.DocType("Attendee")
	query = (frappe.qb.from_(attendee).select(Count("*"))
		.where((attendee.event == event) & attendee.status.isin(SEAT_STATUSES)))
	if for_update:
		query = query.for_update()
	return query.run()[0][0]


def seats_taken(event, exclude_hold=None, for_update=False):
	"""Booked seats plus the seats other visitors hold right now."""
	return booked_seats(event, for_update=for_update) + held_seats(event, exclude=exclude_hold)


def attendee_counts(event):
	rows = frappe.get_all("Attendee", filters={"event": event}, fields=["status", "payment_status"])
	return {
		"registered": sum(1 for r in rows if r.status in SEAT_STATUSES),
		"attended": sum(1 for r in rows if r.status == "Attended"),
		"no_show": sum(1 for r in rows if r.status == "No Show"),
		"cancelled": sum(1 for r in rows if r.status == "Cancelled"),
		"paid": sum(1 for r in rows if r.payment_status == "Paid"),
		"open_payment": sum(1 for r in rows if r.payment_status in ("Pending", "Ordered", "Invoiced")),
	}


def sale_state(doc, now=None, exclude_hold=None, for_update=False):
	"""(open, reason): reason is None or one of closed, no_tax_template, not_started, ended, sold_out,
	cancelled, no_price.
	``for_update``: count with locking reads (see ``booked_seats``)."""
	now = get_datetime(now or now_datetime())
	if doc.status == "Cancelled":
		return False, "cancelled"
	if not doc.published or doc.status not in OPEN_EVENT_STATUSES or not doc.registration_open:
		return False, "closed"
	if doc.get("ticket_item") and not doc.get("item_tax_template"):
		return False, "no_tax_template"  # phamos/phamos#1710: no sale before the tax rate is known
	if doc.get("ticket_sales_from") and now < get_datetime(doc.ticket_sales_from):
		return False, "not_started"
	until = doc.get("ticket_sales_until") or doc.get("starts_on")
	if until and now > get_datetime(until):
		return False, "ended"
	if cint(doc.max_attendees) and seats_taken(doc.name, exclude_hold, for_update=for_update) >= cint(doc.max_attendees):
		return False, "sold_out"
	if doc.get("ticket_item") and not billing.select_price(doc, 1, now, exclude_hold=exclude_hold, for_update=for_update):
		ladder = billing.price_ladder(doc, now, exclude_hold=exclude_hold, for_update=for_update)
		if not ladder:
			return False, "no_price"
		if any(row.upcoming for row in ladder):
			return False, "not_started"
		return False, "sold_out" if any(row.quota and row.remaining == 0 for row in ladder) else "ended"
	return True, None


def is_ticket_sale_open(doc, now=None):
	return sale_state(doc, now)[0]


def offer(event_name):
	"""What the website shows and sells; read-only. None when the event does not exist."""
	if not frappe.db.exists("Marketing Content", event_name):
		return None
	doc = frappe.get_doc("Marketing Content", event_name)
	paid = bool(doc.get("ticket_item"))
	# Without an Item Tax Template there is no price to show (and get_ticket_pricing would refuse).
	pricing = billing.get_ticket_pricing(doc) if paid and doc.get("item_tax_template") else None
	is_open, reason = sale_state(doc)
	capacity = cint(doc.max_attendees) or None
	spots_left = max(0, capacity - seats_taken(doc.name)) if capacity else None
	limit = cint(doc.get("max_attendees_per_order")) or MAX_ATTENDEES_PER_ORDER
	if pricing:
		current = next((r for r in billing.price_ladder(doc) if r.title == pricing.price_title), None)
		if current and current.remaining is not None:
			# An order must fit into one price row.
			limit = min(limit, current.remaining)
	ladder = [{"title": r.title, "gross": r.gross, "net": r.net, "remaining": r.remaining, "quota": r.quota,
		"valid_until": r.valid_until, "valid_from": r.valid_from, "available": r.available, "ended": r.ended,
		"upcoming": r.upcoming} for r in billing.price_ladder(doc)] if pricing else []
	return frappe._dict(
		free=not paid,
		item_name=pricing.item_name if pricing else None,
		price_title=pricing.price_title if pricing else None,
		currency=pricing.currency if pricing else billing.company_currency(),
		net=pricing.net if pricing else 0,
		tax_rate=pricing.tax_rate if pricing else 0,
		gross=pricing.gross if pricing else 0,
		prices=ladder,
		sale_open=is_open,
		reason=reason,
		sale_until=doc.get("ticket_sales_until") or doc.get("starts_on"),
		capacity=capacity,
		spots_left=spots_left,
		max_per_order=min(limit, spots_left if spots_left is not None else limit) or 0,
		terms=doc.get("tc_name"),
		booked=booked_seats(doc.name),
		show_bookings=bool(cint(doc.get("show_bookings_publicly"))),
	)


# --- consent token (optional questions after the order) ---------------------------------------------------

CONSENT_TOKEN_HOURS = 48


def consent_token(reference, exp=None):
	"""``<exp>.<hmac>``: lets the browser that placed the order answer the optional questions afterwards."""
	exp = exp or int(add_to_date(now_datetime(), hours=CONSENT_TOKEN_HOURS).timestamp())
	return f"{exp}.{_sign(reference, exp)}"


def verify_consent_token(reference, token):
	try:
		exp, sig = (token or "").split(".", 1)
		exp = int(exp)
	except ValueError:
		return False
	return exp >= int(now_datetime().timestamp()) and hmac.compare_digest(_sign(reference, exp), sig)


def _sign(reference, exp):
	# The site's secret key; Frappe creates and stores one if the site has none. Never the site name:
	# that is public, and anyone could forge tokens with it (phamos/phamos#1705).
	key = get_encryption_key().encode()
	return hmac.new(key, f"event-consent|{reference}|{exp}".encode(), hashlib.sha256).hexdigest()


# --- the order -------------------------------------------------------------------------------------------


# A web or email address inside a name: "://", "www.", "@", or a domain-like word (a letter, a dot, then two or
# more letters: "evil.example"). "Dr. Müller" and "J. R. R. Tolkien" pass: a space or a single letter follows.
LINK_IN_NAME = re.compile(r"://|www\.|@|[^\W\d_]\.[^\W\d_]{2,}", re.IGNORECASE)


def _clean_person(raw, email_required=True):
	raw = frappe._dict(raw or {})
	first, last = (raw.get("first_name") or "").strip(), (raw.get("last_name") or "").strip()
	if not first:
		first, last = split_name((raw.get("full_name") or "").strip())
	if not first:
		frappe.throw(_("Please enter a name for every ticket."))
	# Names reach strangers' inboxes ("<buyer> booked a ticket for you"): no links (phamos/phamos#1704).
	if any(LINK_IN_NAME.search(value) for value in (first, last, raw.get("full_name") or "")):
		frappe.throw(_("Please enter a name only, without web or email addresses."))
	email = normalize_email(raw.get("email")) if (email_required or (raw.get("email") or "").strip()) else ""
	return frappe._dict(first_name=first[:140], last_name=last[:140], email=email,
		full_name=" ".join(filter(None, [first, last]))[:140],
		phone=(raw.get("phone") or "").strip()[:40], company_name=(raw.get("company_name") or "").strip()[:140],
		job_title=(raw.get("job_title") or "").strip()[:140])


def _clean_billing(raw, contact):
	raw = frappe._dict(raw or {})
	person = _clean_person({"full_name": raw.get("full_name") or contact.full_name,
		"first_name": raw.get("first_name"), "last_name": raw.get("last_name"),
		"email": raw.get("email") or contact.email, "phone": raw.get("phone") or contact.phone,
		"company_name": raw.get("company") or raw.get("company_name")})
	person.is_company = cint(raw.get("is_company")) or bool(person.company_name)
	if person.is_company and not person.company_name:
		frappe.throw(_("Please enter the company name for the invoice."))
	person.update({key: (raw.get(key) or "").strip()[:140] for key in
		("address_line1", "address_line2", "postcode", "city", "country", "vat_id")})
	return person


def register_attendees(event, contact, attends=True, companions=None, billing_data=None, source="Website", lang="de",
		expected_total=None, hold_id=None):
	"""Validate and book an order for ``event`` (Marketing Content name).

	``contact``: the person who orders ({full_name | first_name + last_name, email, phone}); ``attends``:
	whether they hold a ticket themselves. ``companions``: [{full_name, email?}] – without an email, the
	tickets and all information go to the contact's address. ``billing_data``: the invoice address (paid
	events). ``expected_total``: the total the buyer saw; the order is refused when the price changed in
	between (e.g. the early-bird quota ran out).

	Returns {ok, reference, reference_doctype, attendees, paid, tickets_to, consent_token}.
	"""
	result = _register(event, contact, attends, companions, billing_data, source, lang, expected_total, hold_id)
	# Only once the attendees are committed: until then the held seats must still count as taken. A failed
	# order keeps its hold until it expires.
	if hold_id:
		frappe.db.after_commit.add(lambda: release_hold(event, hold_id))
	return result


# The order form's hold id doubles as the order's idempotency key. The browser creates it with
# crypto.randomUUID() (36 characters); shorter ids are not trusted as a secret, because the repeat answer
# carries a consent token.
ORDER_KEY_MIN_LENGTH = 32


def _previous_order(event, order_key, contact):
	"""The result of the order already placed with ``order_key`` for ``event``, or None.

	A locking read under the event lock, so it sees an order that committed while this request waited. The
	first order wins: a repeat with other data gets the first order back and books nothing. Since
	phamos/phamos#1724 the key is on the Event Ticket Order; orders placed before keep it on their Attendees.
	"""
	ticket_order = frappe.qb.DocType("Event Ticket Order")
	found = (frappe.qb.from_(ticket_order).select(ticket_order.name)
		.where((ticket_order.event == event) & (ticket_order.order_key == order_key))
		.orderby(ticket_order.creation).limit(1).for_update().run())
	if found:
		order = frappe.get_doc("Event Ticket Order", found[0][0])
		return _order_result(order, frappe.db.count("Attendee", {"ticket_order": order.name}))
	attendee = frappe.qb.DocType("Attendee")
	rows = (frappe.qb.from_(attendee)
		.select(attendee.name, attendee.order_reference, attendee.is_buyer, attendee.email)
		.where((attendee.event == event) & (attendee.order_key == order_key))
		.orderby(attendee.creation).for_update().run(as_dict=True))
	if not rows:
		return None
	lines = billing.ticket_lines([r.name for r in rows])
	sales_order = next((lines[r.name] for r in rows if r.name in lines), None)
	reference = sales_order or next((r.order_reference for r in rows if r.order_reference), None)
	if sales_order:
		tickets_to = frappe.db.get_value("Sales Order", sales_order, "contact_email")
	else:
		tickets_to = next((r.email for r in rows if r.is_buyer and r.email), None)
	tickets_to = tickets_to or normalize_email((contact or {}).get("email"), throw=False)
	return {"ok": True, "reference": reference, "reference_doctype": "Sales Order" if sales_order else "Attendee",
		"attendees": len(rows), "paid": bool(sales_order), "tickets_to": tickets_to,
		"consent_token": consent_token(reference)}


def _register(event, contact, attends, companions, billing_data, source, lang, expected_total, hold_id=None):
	# Row lock until the request commits: two orders placed at the same moment are booked one after the
	# other. The lock alone is not enough: under REPEATABLE READ, plain reads after it still see the snapshot
	# of the request's first read (the page data, before the lock), so another order that committed while
	# this one waited would be missed. Every count in the order path below this line must therefore use
	# for_update=True, a locking read of the latest committed rows (phamos/phamos#1699).
	doc = frappe.get_doc("Marketing Content", event, for_update=True)
	# Before every other check: a repeat of an order that went through (double click, lost response, reload)
	# must get that order back, not "sold out" or "already registered" (phamos/phamos#1700).
	order_key = hold_id if hold_id and len(hold_id) >= ORDER_KEY_MIN_LENGTH else None
	previous = _previous_order(doc.name, order_key, contact) if order_key else None
	if previous:
		return previous
	is_open, reason = sale_state(doc, exclude_hold=hold_id, for_update=True)
	if not is_open:
		frappe.throw(_("Sorry, registration for this event is not possible ({0}).").format(_(reason)))

	main = _clean_person(contact, email_required=True)
	others = [_clean_person(p, email_required=False) for p in (companions or [])]
	people = ([main] if cint(attends) else []) + others
	limit = cint(doc.get("max_attendees_per_order")) or MAX_ATTENDEES_PER_ORDER
	if not people:
		frappe.throw(_("Please add at least one ticket holder."))
	if len(people) > limit:
		frappe.throw(_("At most {0} tickets per order.").format(limit))
	emails = [p.email for p in people if p.email]
	if len(set(emails)) != len(emails):
		frappe.throw(_("Two tickets have the same email address. Leave the email of a companion empty instead."))
	# The message names no address: anyone can type any email, and it must not tell them who is registered.
	# It still says that one of the typed addresses is registered. That is accepted: a probe of an address
	# that is not registered books a real ticket for that person and mails them, so nobody can test addresses
	# unnoticed (plus 5 orders per hour per IP; phamos/phamos#1702).
	if emails and frappe.db.exists("Attendee", {"event": doc.name, "email": ["in", emails], "status": ["!=", "Cancelled"]}):
		frappe.throw(_("One of these email addresses is already registered for this event. Please check the "
			"addresses, or leave a ticket holder's email empty."))
	taken = seats_taken(doc.name, exclude_hold=hold_id, for_update=True)
	if cint(doc.max_attendees) and taken + len(people) > cint(doc.max_attendees):
		frappe.throw(_("Only {0} seats are left.").format(max(0, cint(doc.max_attendees) - taken)))

	paid = bool(doc.get("ticket_item"))
	pricing = billing.get_ticket_pricing(doc, len(people), exclude_hold=hold_id, for_update=True) if paid else None
	if paid and not pricing:
		frappe.throw(_("There are not enough tickets left at one price for this order. Please order fewer tickets."))
	confirmed_total = billing.order_total(pricing, len(people)).total if pricing else None
	if pricing and expected_total is not None and abs(flt(expected_total) - confirmed_total) >= 0.005:
		frappe.throw(_("The ticket price has changed in the meantime ({0}). Please check your order again.").format(
			pricing.price_title), title=_("Price changed"))

	now = now_datetime()
	buyer = _clean_billing(billing_data, main) if paid else main
	company = buyer.company_name if paid and buyer.is_company else ""
	campaign = crm.get_or_create_campaign(doc)

	def link(person, company_name=""):
		"""The contact form's CRM step for one person (phamos/phamos#1724)."""
		if not person.email:
			return frappe._dict(contact=None, lead=None, customer=None, crm_status="Unlinked")
		match = crm.match_or_create_lead(email=person.email, first_name=person.first_name, last_name=person.last_name,
			company_name=company_name, phone=person.phone, campaign=campaign, source=crm.ensure_lead_source())
		return frappe._dict(match, crm_status="Linked")

	buyer_links = link(main, company or main.company_name)
	# One Event Ticket Order per order (phamos/phamos#1717): the buyer, the billing data as typed and the price
	# the buyer confirmed. No Customer and no Sales Order here: the desk creates them (phamos/phamos#1725).
	order = frappe.get_doc({
		"doctype": "Event Ticket Order", "event": doc.name, "ordered_on": now, "source": source,
		"language": lang if lang in ("de", "en") else None, "order_key": order_key,
		"buyer_first_name": main.first_name, "buyer_last_name": main.last_name, "buyer_email": main.email,
		"buyer_phone": main.phone, "buyer_attends": 1 if cint(attends) else 0,
		"lead": buyer_links.lead, "contact": buyer_links.contact, "customer": buyer_links.customer,
		"ticket_type": pricing.price_title if pricing else "Free", "quantity": len(people),
		"ticket_rate": (pricing.gross if pricing.inclusive else pricing.net) if pricing else 0,
		"ticket_rate_includes_tax": 1 if pricing and pricing.inclusive else 0,
		"item_tax_template": pricing.item_tax_template if pricing else None,
		"confirmed_total": confirmed_total or 0,
		**({"billing_is_company": 1 if buyer.is_company else 0, "billing_name": buyer.full_name,
			"billing_company": buyer.company_name, "billing_vat_id": buyer.vat_id, "billing_email": buyer.email,
			"billing_address_line1": buyer.address_line1, "billing_address_line2": buyer.address_line2,
			"billing_postcode": buyer.postcode, "billing_city": buyer.city,
			"billing_country": _country(buyer.country)} if paid else {}),
	}).insert(ignore_permissions=True)

	docs = []
	for person in people:
		is_buyer = person is main
		links = buyer_links if is_buyer else link(person, company)
		att = frappe.get_doc({
			"doctype": "Attendee", "event": doc.name, "role": "Guest", "status": "Registered", "source": source,
			"language": lang if lang in ("de", "en") else None, "registered_on": now,
			"first_name": person.first_name, "last_name": person.last_name, "email": person.email or None,
			"phone": person.phone, "company_name": company or person.company_name,
			"is_buyer": 1 if is_buyer else 0, "ticket_order": order.name, "order_reference": order.name,
			"contact": links.contact, "lead": links.lead, "customer": links.customer, "crm_status": links.crm_status,
			"ticket_type": pricing.price_title if pricing else "Free",
			# Paid tickets wait for the desk's Sales Order: the order is "Booked" (phamos/phamos#1723).
			"payment_status": "Pending" if paid else "Not Required",
			# The click is the order under the event's terms; the privacy notice was shown to the buyer.
			"terms_accepted": 1, "terms_version": doc.get("tc_name"),
			"privacy_consent": 1 if is_buyer else 0,
			"notes": _("Tickets and information go to {0}.").format(main.email) if not person.email else None,
		})
		att.insert(ignore_permissions=True)
		docs.append(att)

	totals = billing.order_total(pricing, len(people)) if pricing else None
	# Not "event=": frappe.enqueue has a parameter of that name and would swallow it.
	frappe.enqueue("phamos.marketing.ticketing.send_order_confirmation", enqueue_after_commit=True,
		event_name=doc.name, reference=order.name, reference_doctype="Event Ticket Order", recipient=main.email,
		buyer_name=main.full_name, lang=lang, totals=dict(totals) if totals else None)
	# The main contact gets every ticket (above); a ticket holder with an email of their own also gets theirs.
	for att in docs:
		if not att.is_buyer and att.email and att.email != main.email:
			frappe.enqueue("phamos.marketing.ticketing.send_ticket", enqueue_after_commit=True,
				attendee=att.name, buyer_name=main.full_name, lang=lang)
	return _order_result(order, len(docs))


def _country(value):
	"""The Country record for a typed country name, else None (billing data stays as typed otherwise)."""
	from phamos.phamos.doctype.lead_data.crm_handoff import _resolve_country

	return _resolve_country(value) if value else None


def _order_result(order, attendees):
	return {"ok": True, "reference": order.name, "reference_doctype": "Event Ticket Order", "attendees": attendees,
		"paid": bool(order.confirmed_total), "tickets_to": order.buyer_email, "consent_token": consent_token(order.name)}


def save_consents(reference, consents, event=None):
	"""The optional questions after an order: stored on the buyer's Attendee row with timestamps.
	Returns the buyer's email (for the newsletter double opt-in) or None."""
	filters = {"order_reference": reference, **({"event": event} if event else {})}
	rows = frappe.get_all("Attendee", filters=filters, fields=["name", "is_buyer", "email"],
		order_by="creation asc")
	row = next((r for r in rows if r.is_buyer), None)
	values = {"newsletter_consent": cint(consents.get("newsletter")),
		"share_with_attendees_consent": cint(consents.get("attendee_contact")),
		"public_listing_consent": cint(consents.get("public_listing"))}
	if row:
		doc = frappe.get_doc("Attendee", row.name)
		doc.update(values)
		doc.save(ignore_permissions=True)
		return doc.email
	# The buyer holds no ticket: only the newsletter question applies, to the order's email.
	return frappe.db.get_value("Event Ticket Order", reference, "buyer_email") or \
		frappe.db.get_value("Sales Order", reference, "contact_email")


def send_order_confirmation(event_name, reference, recipient, reference_doctype="Event Ticket Order", buyer_name=None,
		lang="de", totals=None):
	"""Order or registration confirmation (§ 312i BGB: confirmation without delay, terms storable).

	``reference``: the Event Ticket Order. ``totals``: {net_total, tax_total, total} as confirmed
	(``billing.order_total``); the invoice follows separately from the desk's Sales Order (phamos/phamos#1724)."""
	from phamos.marketing.web import build_ics
	from phamos.web_profile.sections import find_item

	event = event_name

	doc = frappe.get_doc("Marketing Content", event)
	frappe.local.lang = lang if lang in ("de", "en") else "de"
	attendees = frappe.get_all("Attendee", filters={"event": event, "order_reference": reference},
		fields=["full_name", "email", "ticket_type"], order_by="creation asc")
	order = frappe.get_doc("Event Ticket Order", reference)
	paid = bool(order.confirmed_total)
	# Plain lines, escaped by the template: the billing data was typed by an anonymous buyer.
	address = [line for line in (order.billing_address_line1, order.billing_address_line2,
		" ".join(filter(None, [order.billing_postcode, order.billing_city])),
		_(order.billing_country) if order.billing_country else None) if line] if paid else None
	attachments = []
	item = find_item("events", doc.route, frappe.local.lang) if doc.published else None
	if item and doc.starts_on:
		attachments.append({"fname": f"{item.slug}.ics", "fcontent": build_ics(item, for_attendee=True)})
	terms_html = frappe.db.get_value("Terms and Conditions", doc.tc_name, "terms") if doc.tc_name else None
	if terms_html:
		try:
			from frappe.utils.pdf import get_pdf

			attachments.append({"fname": f"{_('Terms')}-{doc.route}.pdf",
				"fcontent": get_pdf(f"<h1>{frappe.utils.escape_html(doc.title)}</h1>{terms_html}")})
		except Exception:
			frappe.log_error(title="Event order confirmation: terms PDF failed", reference_doctype="Marketing Content",
				reference_name=event)
	subject = (_("Order confirmation {0}: {1}") if paid else _("Your registration {0} for {1}")).format(reference, doc.title)
	frappe.sendmail(
		recipients=[recipient],
		attachments=attachments,
		subject=subject,
		template="event_order_confirmation",
		args={"event": doc, "venue": venue(doc), "reference": reference, "attendees": attendees, "paid": paid,
			"order": order, "totals": frappe._dict(totals or {}), "currency": billing.company_currency(),
			"address": address, "buyer_name": buyer_name, "recipient": recipient,
			"terms_attached": any(a["fname"].endswith(".pdf") for a in attachments),
			"terms_html": terms_html if not any(a["fname"].endswith(".pdf") for a in attachments) else None,
			"event_url": frappe.utils.get_url(item.url) if item else None,
			"privacy_url": frappe.utils.get_url("/en/privacy" if lang == "en" else "/de/datenschutz"),
			"imprint_url": frappe.utils.get_url("/en/imprint" if lang == "en" else "/de/impressum")},
		reference_doctype=reference_doctype,
		reference_name=reference,
	)


def venue(doc):
	"""Where the event takes place, for the emails: the meeting link of an online event (attendees only),
	else the address as plain text (the email program decides whether it opens a map)."""
	from phamos.marketing.location import address_line, is_online

	if is_online(doc):
		return {"online": True, "link": doc.location}
	text = address_line(doc)
	return {"text": text} if text else None


TICKET_MAIL_DAILY_LIMIT = 200


def _ticket_mail_allowed(att):
	"""At most ``event_ticket_mail_daily_limit`` (site config, default 200) companion ticket mails per event and
	day: the addresses are nobody's confirmed ones, so a script must not turn orders into a mail relay
	(phamos/phamos#1704). Above the limit the mail is not sent; staff see why and can send it from the desk."""
	limit = cint(frappe.conf.get("event_ticket_mail_daily_limit")) or TICKET_MAIL_DAILY_LIMIT
	key = frappe.cache.make_key(f"event_ticket_mails:{att.event}:{nowdate()}")
	sent = frappe.cache.incr(key)
	if sent == 1:
		frappe.cache.expire(key, 2 * 24 * 60 * 60)
	if sent <= limit:
		return True
	att.add_comment("Comment", _("Ticket mail not sent: daily limit of {0} reached for this event.").format(limit))
	if sent == limit + 1:
		frappe.log_error(title=_("Event ticket mails: daily limit reached"),
			message=f"Event {att.event}: more than {limit} companion ticket mails today.",
			reference_doctype="Marketing Content", reference_name=att.event)
	return False


def send_ticket(attendee, buyer_name=None, lang="de", ignore_limit=False):
	"""A ticket holder's own ticket: name, event, date, venue and the calendar file. No prices and no
	billing details: those belong to the buyer, who got the full confirmation with every ticket.

	``ignore_limit``: sent by staff from the desk ("Send Ticket"), not counted against the daily limit."""
	from phamos.marketing.web import build_ics
	from phamos.web_profile.sections import find_item

	att = frappe.get_doc("Attendee", attendee)
	if not att.email:
		return
	if not ignore_limit and not _ticket_mail_allowed(att):
		return
	doc = frappe.get_doc("Marketing Content", att.event)
	frappe.local.lang = lang if lang in ("de", "en") else "de"
	item = find_item("events", doc.route, frappe.local.lang) if doc.published else None
	attachments = [{"fname": f"{item.slug}.ics", "fcontent": build_ics(item, for_attendee=True)}] if item and doc.starts_on else []
	frappe.sendmail(
		recipients=[att.email],
		attachments=attachments,
		subject=_("Your ticket for {0}").format(doc.title),
		template="event_ticket",
		args={"event": doc, "venue": venue(doc), "attendee": att, "buyer_name": buyer_name, "reference": att.order_reference,
			"event_url": frappe.utils.get_url(item.url) if item else None,
			"privacy_url": frappe.utils.get_url("/en/privacy" if lang == "en" else "/de/datenschutz"),
			"imprint_url": frappe.utils.get_url("/en/imprint" if lang == "en" else "/de/impressum")},
		reference_doctype="Attendee",
		reference_name=att.name,
	)

