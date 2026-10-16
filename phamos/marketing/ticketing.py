"""Ticket sale and registration for one event: what is on offer, and the order itself.

``register_attendees`` is the single server-side entry for website orders. It validates everything the
browser could have skipped, re-calculates the price the buyer confirmed, creates the buyer's Customer
(paid events) or Lead (free events) with Contact and Address, one Attendee per ticket holder and, for
paid events, a submitted Sales Order: the click on "Zahlungspflichtig bestellen" is the binding order.
It runs as the "Event Ticketing" service user and never commits: the request commits on success and
rolls back on any error.
"""

from contextlib import contextmanager

import hashlib
import hmac
import time

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, now_datetime

from phamos.marketing import billing, crm
from phamos.marketing.defaults import FREE_BOOKING_SERIES, MAX_ATTENDEES_PER_ORDER, SEAT_STATUSES
from phamos.marketing.utils import normalize_email, split_name

OPEN_EVENT_STATUSES = ("Upcoming", "Ongoing")


@contextmanager
def ticketing_session():
	"""Run a website order as the "Event Ticketing" service user instead of Guest (see marketing.setup).

	Desk users keep their own session. ``frappe.set_user`` clears ``form_dict``: read all request
	arguments before entering.
	"""
	from phamos.marketing.setup import TICKETING_USER, ensure_ticketing_user

	if frappe.session.user != "Guest":
		yield
		return
	if not frappe.db.exists("User", TICKETING_USER):
		ensure_ticketing_user()
	frappe.set_user(TICKETING_USER)
	try:
		yield
	finally:
		frappe.set_user("Guest")


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


def hold_seats(event_doc, hold_id, qty):
	"""Reserve ``qty`` seats (and the price that applies to them) for 20 minutes; renewed on every call.

	Returns {ok, expires (ms since epoch), price_title, gross, spots_left, max_per_order} or {ok: False, reason}.
	"""
	qty = max(1, cint(qty))
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
		"price_title": pricing.price_title if pricing else None})
	return {"ok": True, "expires": int(expires * 1000), "minutes": HOLD_MINUTES,
		"price_title": pricing.price_title if pricing else None, "gross": pricing.gross if pricing else 0,
		"spots_left": max(0, capacity - taken - qty) if capacity else None}


def booked_seats(event):
	"""Seats of registered attendees (no holds): what the page may show as "booked"."""
	return frappe.db.count("Attendee", {"event": event, "status": ["in", SEAT_STATUSES]})


def seats_taken(event, exclude_hold=None):
	"""Booked seats plus the seats other visitors hold right now."""
	return booked_seats(event) + held_seats(event, exclude=exclude_hold)


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


def sale_state(doc, now=None, exclude_hold=None):
	"""(open, reason): reason is None or one of closed, not_started, ended, sold_out, cancelled, no_price."""
	now = get_datetime(now or now_datetime())
	if doc.status == "Cancelled":
		return False, "cancelled"
	if not doc.published or doc.status not in OPEN_EVENT_STATUSES or not doc.registration_open:
		return False, "closed"
	if doc.get("ticket_sales_from") and now < get_datetime(doc.ticket_sales_from):
		return False, "not_started"
	until = doc.get("ticket_sales_until") or doc.get("starts_on")
	if until and now > get_datetime(until):
		return False, "ended"
	if cint(doc.max_attendees) and seats_taken(doc.name, exclude_hold) >= cint(doc.max_attendees):
		return False, "sold_out"
	if doc.get("ticket_item") and not billing.select_price(doc, 1, now, exclude_hold=exclude_hold):
		ladder = billing.price_ladder(doc, now, exclude_hold=exclude_hold)
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
	pricing = billing.get_ticket_pricing(doc) if paid else None
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
		"upcoming": r.upcoming} for r in billing.price_ladder(doc)] if paid else []
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
	key = (frappe.local.conf.get("encryption_key") or frappe.local.site).encode()
	return hmac.new(key, f"event-consent|{reference}|{exp}".encode(), hashlib.sha256).hexdigest()


# --- the order -------------------------------------------------------------------------------------------


def _clean_person(raw, email_required=True):
	raw = frappe._dict(raw or {})
	first, last = (raw.get("first_name") or "").strip(), (raw.get("last_name") or "").strip()
	if not first:
		first, last = split_name((raw.get("full_name") or "").strip())
	if not first:
		frappe.throw(_("Please enter a name for every ticket."))
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
	with ticketing_session():
		result = _register(event, contact, attends, companions, billing_data, source, lang, expected_total, hold_id)
	release_hold(event, hold_id)
	return result


def _register(event, contact, attends, companions, billing_data, source, lang, expected_total, hold_id=None):
	doc = frappe.get_doc("Marketing Content", event)
	is_open, reason = sale_state(doc, exclude_hold=hold_id)
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
	existing = frappe.get_all("Attendee", filters={"event": doc.name, "email": ["in", emails],
		"status": ["!=", "Cancelled"]}, pluck="email") if emails else []
	if existing:
		frappe.throw(_("Already registered for this event: {0}").format(", ".join(existing)))
	taken = seats_taken(doc.name, exclude_hold=hold_id)
	if cint(doc.max_attendees) and taken + len(people) > cint(doc.max_attendees):
		frappe.throw(_("Only {0} seats are left.").format(max(0, cint(doc.max_attendees) - taken)))

	paid = bool(doc.get("ticket_item"))
	pricing = billing.get_ticket_pricing(doc, len(people), exclude_hold=hold_id) if paid else None
	if paid and not pricing:
		frappe.throw(_("There are not enough tickets left at one price for this order. Please order fewer tickets."))
	if pricing and expected_total is not None and abs(flt(expected_total) - flt(pricing.gross * len(people), 2)) > 0.01:
		frappe.throw(_("The ticket price has changed in the meantime ({0}). Please check your order again.").format(
			pricing.price_title), title=_("Price changed"))

	now = now_datetime()
	if paid:
		buyer = _clean_billing(billing_data, main)
		party = crm.ensure_customer(buyer, doc, lang)
		customer, buyer_contact = party.customer, party.contact
		buyer_links = frappe._dict(contact=buyer_contact, lead=None, customer=customer,
			crm_status="Needs Review" if party.review else "Linked")
	else:
		buyer = main
		buyer_links = crm.resolve_party(email=main.email, first_name=main.first_name, last_name=main.last_name,
			phone=main.phone, event=doc)
		customer = buyer_links.customer

	docs = []
	for person in people:
		is_buyer = person is main
		if is_buyer:
			links = buyer_links
		elif not person.email:
			links = frappe._dict(contact=None, lead=None, customer=None, crm_status="Unlinked")
		else:
			links = crm.resolve_party(email=person.email, first_name=person.first_name, last_name=person.last_name,
				company_name=buyer.company_name if paid and buyer.is_company else "", event=doc,
				link_to_customer=customer if paid and buyer.is_company else None)
		att = frappe.get_doc({
			"doctype": "Attendee", "event": doc.name, "role": "Guest", "status": "Registered", "source": source,
			"language": lang if lang in ("de", "en") else None, "registered_on": now,
			"first_name": person.first_name, "last_name": person.last_name, "email": person.email or None,
			"phone": person.phone, "company_name": buyer.company_name if paid and buyer.is_company else person.company_name,
			"is_buyer": 1 if is_buyer else 0,
			"contact": links.contact, "lead": links.lead, "customer": links.customer, "crm_status": links.crm_status,
			"ticket_type": pricing.price_title if pricing else "Free",
			"payment_status": "Pending" if paid else "Not Required",
			# The click is the order under the event's terms; the privacy notice was shown to the buyer.
			"terms_accepted": 1, "terms_version": doc.get("tc_name"),
			"privacy_consent": 1 if is_buyer else 0,
			"notes": _("Tickets and information go to {0}.").format(main.email) if not person.email else None,
		})
		att.insert(ignore_permissions=True)
		docs.append(att)
	if paid and party.review:
		for att in docs:
			if att.is_buyer:
				att.add_comment("Comment", _("Possible duplicate Customer: {0} has the same company name as {1}.").format(
					customer, party.review))

	if paid:
		so = billing.create_sales_order(doc, docs, customer, pricing=pricing, submit=True, contact=buyer_contact,
			address=party.address, email=buyer.email, lang=lang)
		reference, reference_doctype = so.name, "Sales Order"
	else:
		reference, reference_doctype = frappe.model.naming.make_autoname(FREE_BOOKING_SERIES), "Attendee"
		for att in docs:
			frappe.db.set_value("Attendee", att.name, "order_reference", reference, update_modified=False)

	# Enqueued inside the service session: the job runs as the service user (background_jobs.enqueue).
	# Not "event=": frappe.enqueue has a parameter of that name and would swallow it.
	frappe.enqueue("phamos.marketing.ticketing.send_order_confirmation", enqueue_after_commit=True,
		event_name=doc.name, reference=reference, reference_doctype=reference_doctype, recipient=main.email,
		buyer_name=main.full_name, lang=lang)
	return {"ok": True, "reference": reference, "reference_doctype": reference_doctype, "attendees": len(docs),
		"paid": paid, "tickets_to": main.email, "consent_token": consent_token(reference)}


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
	return frappe.db.get_value("Sales Order", reference, "contact_email")


def send_order_confirmation(event_name, reference, recipient, reference_doctype="Sales Order", buyer_name=None,
		lang="de"):
	"""Order or registration confirmation (§ 312i BGB: confirmation without delay, terms storable)."""
	from phamos.marketing.web import build_ics
	from phamos.web_profile.sections import find_item

	event = event_name

	doc = frappe.get_doc("Marketing Content", event)
	frappe.local.lang = lang if lang in ("de", "en") else "de"
	attendees = frappe.get_all("Attendee", filters={"event": event, "order_reference": reference},
		fields=["full_name", "email", "ticket_type"], order_by="creation asc")
	order = frappe.get_doc("Sales Order", reference) if reference_doctype == "Sales Order" else None
	address = None
	if order and order.customer_address:
		from frappe.contacts.doctype.address.address import get_address_display

		address = get_address_display(order.customer_address)
	attachments = []
	item = find_item("events", doc.route, frappe.local.lang) if doc.published else None
	if item and doc.starts_on:
		attachments.append({"fname": f"{item.slug}.ics", "fcontent": build_ics(item)})
	terms_html = frappe.db.get_value("Terms and Conditions", doc.tc_name, "terms") if doc.tc_name else None
	if terms_html:
		try:
			from frappe.utils.pdf import get_pdf

			attachments.append({"fname": f"{_('Terms')}-{doc.route}.pdf",
				"fcontent": get_pdf(f"<h1>{frappe.utils.escape_html(doc.title)}</h1>{terms_html}")})
		except Exception:
			frappe.log_error(title="Event order confirmation: terms PDF failed", reference_doctype="Marketing Content",
				reference_name=event)
	subject = (_("Order confirmation {0}: {1}") if order else _("Your registration {0} for {1}")).format(reference, doc.title)
	frappe.sendmail(
		recipients=[recipient],
		attachments=attachments,
		subject=subject,
		template="event_order_confirmation",
		args={"event": doc, "reference": reference, "attendees": attendees, "order": order, "address": address,
			"buyer_name": buyer_name, "recipient": recipient,
			"terms_attached": any(a["fname"].endswith(".pdf") for a in attachments),
			"terms_html": terms_html if not any(a["fname"].endswith(".pdf") for a in attachments) else None,
			"event_url": frappe.utils.get_url(item.url) if item else None,
			"privacy_url": frappe.utils.get_url("/en/privacy" if lang == "en" else "/de/datenschutz"),
			"imprint_url": frappe.utils.get_url("/en/imprint" if lang == "en" else "/de/impressum")},
		reference_doctype=reference_doctype if order else "Marketing Content",
		reference_name=reference if order else event,
	)
