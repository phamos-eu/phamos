"""Ticket sale and registration for one event: what is on offer, and the order itself.

``register_attendees`` is the single server-side entry for website orders (and later the desk). It
validates everything the browser could have skipped, finds or creates the CRM records, creates one
Attendee per person and, for paid events, a submitted Quotation. It never elevates the session user
and never commits: the request commits on success and rolls back on any error.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from phamos.marketing import billing, crm
from phamos.marketing.defaults import (
	CONSENT_FIELDS,
	FREE_BOOKING_SERIES,
	MAX_ATTENDEES_PER_ORDER,
	SEAT_STATUSES,
)
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


def seats_taken(event):
	return frappe.db.count("Attendee", {"event": event, "status": ["in", SEAT_STATUSES]})


def attendee_counts(event):
	rows = frappe.get_all("Attendee", filters={"event": event}, fields=["status", "payment_status"])
	return {
		"registered": sum(1 for r in rows if r.status in SEAT_STATUSES),
		"attended": sum(1 for r in rows if r.status == "Attended"),
		"no_show": sum(1 for r in rows if r.status == "No Show"),
		"cancelled": sum(1 for r in rows if r.status == "Cancelled"),
		"paid": sum(1 for r in rows if r.payment_status == "Paid"),
		"open_payment": sum(1 for r in rows if r.payment_status in ("Pending", "Quoted", "Ordered", "Invoiced")),
	}


def sale_state(doc, now=None):
	"""(open, reason): reason is None or one of closed, not_started, ended, sold_out, cancelled."""
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
	if cint(doc.max_attendees) and seats_taken(doc.name) >= cint(doc.max_attendees):
		return False, "sold_out"
	return True, None


def is_ticket_sale_open(doc, now=None):
	return sale_state(doc, now)[0]


def offer(event_name):
	"""What the website shows and sells; read-only. None when the event does not exist."""
	if not frappe.db.exists("Marketing Content", event_name):
		return None
	doc = frappe.get_cached_doc("Marketing Content", event_name)
	pricing = billing.get_ticket_pricing(doc)
	is_open, reason = sale_state(doc)
	capacity = cint(doc.max_attendees) or None
	spots_left = max(0, capacity - seats_taken(doc.name)) if capacity else None
	return frappe._dict(
		free=not pricing,
		item_name=pricing.item_name if pricing else None,
		currency=pricing.currency if pricing else None,
		net=pricing.rate if pricing else 0,
		tax_rate=pricing.tax_rate if pricing else 0,
		gross=pricing.gross if pricing else 0,
		sale_open=is_open,
		reason=reason,
		sale_until=doc.get("ticket_sales_until") or doc.get("starts_on"),
		capacity=capacity,
		spots_left=spots_left,
		max_per_order=min(cint(doc.get("max_attendees_per_order")) or MAX_ATTENDEES_PER_ORDER,
			spots_left if spots_left is not None else MAX_ATTENDEES_PER_ORDER) or 0,
		terms=doc.get("tc_name"),
	)


# --- the order -------------------------------------------------------------------------------------------


def _clean_person(raw):
	raw = frappe._dict(raw or {})
	first, last = (raw.get("first_name") or "").strip(), (raw.get("last_name") or "").strip()
	if not first:
		first, last = split_name((raw.get("full_name") or "").strip())
	if not first:
		frappe.throw(_("Please enter a name for every ticket."))
	return frappe._dict(first_name=first[:140], last_name=last[:140], email=normalize_email(raw.get("email")),
		phone=(raw.get("phone") or "").strip()[:40], company_name=(raw.get("company_name") or "").strip()[:140],
		job_title=(raw.get("job_title") or "").strip()[:140])


def _clean_billing(raw, first_attendee):
	if not raw:
		return frappe._dict(first_attendee, is_company=0)
	raw = frappe._dict(raw)
	person = _clean_person({"full_name": raw.get("full_name") or raw.get("invoice_recipient"),
		"first_name": raw.get("first_name"), "last_name": raw.get("last_name"),
		"email": raw.get("email") or first_attendee.email, "phone": raw.get("phone"),
		"company_name": raw.get("company") or raw.get("company_name")})
	person.is_company = cint(raw.get("is_company")) or bool(person.company_name)
	if person.is_company and not person.company_name:
		frappe.throw(_("Please enter the company name for the invoice."))
	person.update({key: (raw.get(key) or "").strip()[:140] for key in
		("address_line1", "address_line2", "postcode", "city", "country", "vat_id")})
	return person


def _check_consents(consents):
	consents = frappe._dict(consents or {})
	values = {field: cint(consents.get(field)) for field in CONSENT_FIELDS}
	# Website keys: terms / privacy / newsletter / attendee_contact / public_listing.
	for key, field in (("terms", "terms_accepted"), ("privacy", "privacy_consent"), ("newsletter", "newsletter_consent"),
			("attendee_contact", "share_with_attendees_consent"), ("public_listing", "public_listing_consent")):
		values[field] = values[field] or cint(consents.get(key))
	if not values["terms_accepted"] or not values["privacy_consent"]:
		frappe.throw(_("Please accept the terms and the privacy policy."))
	return values


def register_attendees(event, attendees, billing_data=None, consents=None, source="Website", lang="de"):
	"""Validate and book an order for ``event`` (Marketing Content name).

	``attendees``: [{full_name | first_name + last_name, email, ...}], the first is the buyer unless
	``billing_data`` names someone else. Returns {ok, reference, reference_doctype, attendees, paid}.
	"""
	with ticketing_session():
		return _register(event, attendees, billing_data, consents, source, lang)


def _register(event, attendees, billing_data, consents, source, lang):
	doc = frappe.get_doc("Marketing Content", event)
	is_open, reason = sale_state(doc)
	if not is_open:
		frappe.throw(_("Sorry, registration for this event is not possible ({0}).").format(_(reason)))

	people = [_clean_person(p) for p in (attendees or [])]
	limit = cint(doc.get("max_attendees_per_order")) or MAX_ATTENDEES_PER_ORDER
	if not people:
		frappe.throw(_("Please add at least one ticket holder."))
	if len(people) > limit:
		frappe.throw(_("At most {0} tickets per order.").format(limit))
	emails = [p.email for p in people]
	if len(set(emails)) != len(emails):
		frappe.throw(_("Every ticket needs its own email address."))
	existing = frappe.get_all("Attendee", filters={"event": doc.name, "email": ["in", emails],
		"status": ["!=", "Cancelled"]}, pluck="email")
	if existing:
		frappe.throw(_("Already registered for this event: {0}").format(", ".join(existing)))
	if cint(doc.max_attendees) and seats_taken(doc.name) + len(people) > cint(doc.max_attendees):
		frappe.throw(_("Only {0} seats are left.").format(max(0, cint(doc.max_attendees) - seats_taken(doc.name))))
	consent_values = _check_consents(consents)

	buyer = _clean_billing(billing_data, people[0])
	pricing = billing.get_ticket_pricing(doc)

	# The buyer: existing Customer (strong email match) or a Lead with Contact and billing Address.
	found = crm.find_party(buyer.email, buyer.company_name)
	buyer_party = crm.resolve_party(email=buyer.email, first_name=buyer.first_name, last_name=buyer.last_name,
		company_name=buyer.company_name, phone=buyer.phone, event=doc)
	party_type, party = ("Customer", buyer_party.customer) if buyer_party.customer else ("Lead", buyer_party.lead)
	if buyer.get("address_line1") and buyer.get("city"):
		crm.create_address(title=buyer.company_name or f"{buyer.first_name} {buyer.last_name}".strip(),
			address_line1=buyer.address_line1, address_line2=buyer.address_line2, city=buyer.city,
			pincode=buyer.postcode, country=buyer.country, email=buyer.email, phone=buyer.phone,
			links=[(party_type, party)])
	if buyer.get("vat_id") and party_type == "Customer" and not frappe.db.get_value("Customer", party, "tax_id"):
		frappe.db.set_value("Customer", party, "tax_id", buyer.vat_id)

	now = now_datetime()
	reference = None if pricing else frappe.model.naming.make_autoname(FREE_BOOKING_SERIES)
	docs = []
	for person in people:
		is_buyer = person.email == buyer.email
		if is_buyer:
			party_links = buyer_party
		else:
			party_links = crm.resolve_party(email=person.email, first_name=person.first_name,
				last_name=person.last_name, company_name=person.company_name or (buyer.company_name if buyer.is_company else ""),
				phone=person.phone, event=doc, link_to_lead=buyer_party.lead if buyer.is_company and party_type == "Lead" else None)
		att = frappe.get_doc({
			"doctype": "Attendee", "event": doc.name, "role": "Guest", "status": "Registered", "source": source,
			"language": lang if lang in ("de", "en") else None, "registered_on": now,
			"first_name": person.first_name, "last_name": person.last_name, "email": person.email,
			"phone": person.phone, "company_name": person.company_name or (buyer.company_name if buyer.is_company else ""),
			"job_title": person.job_title, "is_buyer": 1 if is_buyer else 0,
			"contact": party_links.contact, "lead": party_links.lead, "customer": party_links.customer,
			"crm_status": "Needs Review" if is_buyer and found.confidence == "review" else party_links.crm_status,
			"ticket_type": "Regular" if pricing else "Free",
			"payment_status": "Pending" if pricing else "Not Required",
			"order_reference": reference, "terms_version": doc.get("tc_name"),
			**consent_values,
		})
		att.insert(ignore_permissions=True)
		docs.append(att)

	result = {"ok": True, "attendees": len(docs), "paid": bool(pricing)}
	if pricing:
		qtn = billing.create_quotation(doc, docs, party_type, party, buyer_email=buyer.email)
		result.update(reference=qtn.name, reference_doctype="Quotation")
	else:
		result.update(reference=reference, reference_doctype="Attendee")

	frappe.enqueue("phamos.marketing.ticketing.send_order_confirmation", enqueue_after_commit=True,
		event=doc.name, reference=result["reference"], recipient=buyer.email, lang=lang)
	return result


def send_order_confirmation(event, reference, recipient, lang="de"):
	doc = frappe.get_doc("Marketing Content", event)
	frappe.local.lang = lang if lang in ("de", "en") else "de"
	attendees = frappe.get_all("Attendee", filters={"event": event, "order_reference": reference},
		fields=["full_name", "email"], order_by="creation asc")
	pricing = billing.get_ticket_pricing(doc)
	attachments = []
	if doc.starts_on and doc.published:
		from phamos.marketing.web import build_ics
		from phamos.web_profile.sections import find_item

		item = find_item("events", doc.route, frappe.local.lang)
		if item:
			attachments.append({"fname": f"{item.slug}.ics", "fcontent": build_ics(item)})
	frappe.sendmail(
		recipients=[recipient],
		attachments=attachments,
		subject=_("Your registration {0} for {1}").format(reference, doc.title),
		template="event_order_confirmation",
		args={"event": doc, "reference": reference, "attendees": attendees, "paid": bool(pricing),
			"pricing": pricing, "total": (pricing.gross * len(attendees)) if pricing else 0},
		reference_doctype="Marketing Content",
		reference_name=event,
	)
