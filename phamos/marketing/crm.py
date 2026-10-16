"""Who is this person in our CRM? Contact, Lead and Customer for attendees and buyers.

Rules (phamos/phamos#1169):

1. A Contact with the email exists: use it; if it is linked to exactly one Customer, that is the party.
2. Else a Lead with the email exists: reuse it (a Converted Lead brings its Customer).
3. Else, when allowed, create a Lead (source "Event", the event's Campaign) and its Contact.

A Customer is never created here for website requests: ERPNext creates it when a phamos person turns
the Quotation into a Sales Order (or from the desk with ``ensure_customer_for_order``). A company name
that matches a Customer without an email link is only a hint (``crm_status`` "Needs Review"): a person
decides, so no duplicate or wrong Customer is created.
"""

import re

import frappe
from frappe import _

from phamos.marketing.defaults import LEAD_SOURCE
from phamos.marketing.utils import join_name, normalize_email

_LEGAL_FORMS = re.compile(r"\b(gmbh|ag|kg|ug|ohg|gbr|e\.?\s?v|mbh|co|ltd|inc|llc|se|haftungsbeschränkt)\b\.?", re.I)


def normalize_company(value):
	"""Comparable company name: lower case, without legal form and punctuation."""
	value = _LEGAL_FORMS.sub(" ", (value or "").lower())
	return " ".join(re.sub(r"[^\w\s]", " ", value).split())


# --- lookups --------------------------------------------------------------------------------------------


def contact_for_email(email):
	if not email:
		return None
	return frappe.db.get_value("Contact Email", {"email_id": email, "parenttype": "Contact"}, "parent") or \
		frappe.db.get_value("Contact", {"email_id": email}, "name")


def customers_of_contact(contact):
	if not contact:
		return []
	return frappe.get_all("Dynamic Link", filters={"parenttype": "Contact", "parent": contact,
		"link_doctype": "Customer"}, pluck="link_name", distinct=True)


def lead_for_email(email):
	if not email:
		return None
	return frappe.db.get_value("Lead", {"email_id": email}, "name")


def suggest_customer_for_company(company_name, limit=5):
	"""Customers whose name matches the company: exact (100) or containing it (70)."""
	wanted = normalize_company(company_name)
	if len(wanted) < 3:
		return []
	first_word = wanted.split()[0]
	candidates = frappe.get_all("Customer", filters={"disabled": 0, "customer_name": ["like", f"%{first_word}%"]},
		fields=["name", "customer_name", "customer_type"], limit_page_length=50)
	result = []
	for row in candidates:
		have = normalize_company(row.customer_name)
		score = 100 if have == wanted else 70 if wanted in have or have in wanted else 0
		if score:
			result.append({"customer": row.name, "customer_name": row.customer_name, "score": score})
	result.sort(key=lambda r: -r["score"])
	return result[:limit]


def find_party(email, company_name=None):
	"""Everything we know for an email address, without creating anything.

	``confidence``: "strong" when the email leads to exactly one Customer, "review" when only the
	company name matches a Customer (or the Contact belongs to several), else "none".
	"""
	email = normalize_email(email, throw=False)
	contact = contact_for_email(email)
	customers = customers_of_contact(contact)
	lead = lead_for_email(email)
	customer = customers[0] if len(customers) == 1 else None
	if not customer and lead:
		customer = frappe.db.get_value("Lead", lead, "customer") or \
			frappe.db.get_value("Customer", {"lead_name": lead}, "name")
	matches = [] if customer or not company_name else suggest_customer_for_company(company_name)
	company_match = matches[0]["customer"] if matches and matches[0]["score"] == 100 else None
	if customer:
		confidence = "strong"
	elif len(customers) > 1 or company_match:
		confidence = "review"
	else:
		confidence = "none"
	return frappe._dict(email=email, contact=contact, customers=customers, customer=customer, lead=lead,
		company_match=company_match, suggestions=matches, confidence=confidence)


# --- creation -------------------------------------------------------------------------------------------


def ensure_lead_source(name=LEAD_SOURCE):
	if not frappe.db.exists("Lead Source", name):
		frappe.get_doc({"doctype": "Lead Source", "source_name": name}).insert(ignore_permissions=True)
	return name


def get_or_create_campaign(event_doc):
	"""The event's Campaign (standard ERPNext attribution on Lead, Quotation, Sales Order, Invoice)."""
	if event_doc.get("campaign") and frappe.db.exists("Campaign", event_doc.campaign):
		return event_doc.campaign
	name = frappe.db.get_value("Campaign", {"campaign_name": event_doc.title})
	if not name:
		campaign = frappe.get_doc({"doctype": "Campaign", "campaign_name": event_doc.title,
			"description": _("Event: {0}").format(event_doc.title)})
		campaign.insert(ignore_permissions=True)
		name = campaign.name
	frappe.db.set_value("Marketing Content", event_doc.name, "campaign", name, update_modified=False)
	event_doc.campaign = name
	return name


def create_lead(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		campaign=None):
	lead = frappe.get_doc({
		"doctype": "Lead",
		"first_name": first_name or email.split("@")[0],
		"last_name": last_name,
		"lead_name": join_name(first_name, last_name) or email,
		"email_id": email,
		"mobile_no": phone or None,
		"company_name": company_name or None,
		"job_title": job_title or None,
		"salutation": salutation if salutation and frappe.db.exists("Salutation", salutation) else None,
		"status": "Lead",
		"source": ensure_lead_source(),
		"campaign_name": campaign,
	})
	lead.insert(ignore_permissions=True)
	return lead.name


def create_contact(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		links=()):
	contact = frappe.new_doc("Contact")
	contact.first_name = first_name or email.split("@")[0]
	contact.last_name = last_name
	contact.company_name = company_name
	contact.designation = job_title
	if salutation and frappe.db.exists("Salutation", salutation):
		contact.salutation = salutation
	contact.append("email_ids", {"email_id": email, "is_primary": 1})
	if phone:
		contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1})
	for doctype, name in links:
		if name:
			contact.append("links", {"link_doctype": doctype, "link_name": name})
	contact.insert(ignore_permissions=True)
	return contact.name


def ensure_contact_links(contact, links):
	"""Add missing Dynamic Links (doctype, name) to a Contact."""
	if not contact:
		return
	doc = frappe.get_doc("Contact", contact)
	existing = {(row.link_doctype, row.link_name) for row in doc.links}
	missing = [(dt, name) for dt, name in links if name and (dt, name) not in existing]
	for doctype, name in missing:
		doc.append("links", {"link_doctype": doctype, "link_name": name})
	if missing:
		doc.save(ignore_permissions=True)


def create_address(*, title, address_line1, city, country, pincode="", address_line2="", email="", phone="",
		links=()):
	from phamos.phamos.doctype.lead_data.crm_handoff import _resolve_country

	address = frappe.get_doc({
		"doctype": "Address",
		"address_title": (title or _("Billing"))[:140],
		"address_type": "Billing",
		"address_line1": address_line1,
		"address_line2": address_line2 or None,
		"city": city,
		"pincode": pincode or None,
		"country": _resolve_country(country) or "Germany",
		"email_id": email or None,
		"phone": phone or None,
		"is_primary_address": 1,
		"links": [{"link_doctype": dt, "link_name": name} for dt, name in links if name],
	})
	address.insert(ignore_permissions=True)
	return address.name


def resolve_party(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		event=None, create=True, link_to_lead=None):
	"""Contact + Lead or Customer for one person (rules in the module docstring).

	``link_to_lead``: the buyer's Lead for companions of a company order; their Contacts are linked to it,
	so ERPNext moves them to the Customer when the Lead is converted.
	"""
	found = find_party(email, company_name)
	result = frappe._dict(contact=found.contact, lead=found.lead, customer=found.customer, created=[],
		crm_status="Linked" if found.confidence == "strong" else "Needs Review" if found.confidence == "review"
		else "Unlinked", suggestions=found.suggestions)
	if not create:
		if found.contact or found.lead:
			result.crm_status = result.crm_status if result.crm_status != "Unlinked" else "Linked"
		return result

	person = dict(email=found.email, first_name=first_name, last_name=last_name, company_name=company_name,
		phone=phone, job_title=job_title, salutation=salutation)
	campaign = get_or_create_campaign(event) if event is not None else None

	if not result.customer and not result.lead and not link_to_lead:
		result.lead = create_lead(campaign=campaign, **person)
		result.created.append(("Lead", result.lead))
		# ERPNext may have created the Lead's Contact (CRM Settings "Auto Creation of Contact").
		result.contact = result.contact or contact_for_email(found.email)
	elif result.lead and company_name and not frappe.db.get_value("Lead", result.lead, "company_name"):
		frappe.db.set_value("Lead", result.lead, "company_name", company_name)

	links = [("Customer", result.customer)] if result.customer else [("Lead", result.lead or link_to_lead)]
	if not result.contact:
		result.contact = create_contact(links=links, **person)
		result.created.append(("Contact", result.contact))
	else:
		ensure_contact_links(result.contact, links)

	if result.crm_status == "Unlinked":
		result.crm_status = "Linked"
	return result


def link_attendee(attendee, create=True):
	"""Resolve one Attendee and store contact / lead / customer / crm_status on it."""
	doc = frappe.get_doc("Attendee", attendee) if isinstance(attendee, str) else attendee
	event = frappe.get_doc("Marketing Content", doc.event)
	result = resolve_party(email=doc.email, first_name=doc.first_name, last_name=doc.last_name,
		company_name=doc.company_name, phone=doc.phone, job_title=doc.job_title, salutation=doc.salutation,
		event=event, create=create)
	values = {"contact": result.contact, "lead": result.lead, "customer": result.customer,
		"crm_status": result.crm_status}
	frappe.db.set_value("Attendee", doc.name, values)
	return {**values, "attendee": doc.name, "created": result.created, "suggestions": result.suggestions}


def ensure_customer_for_order(buyer, group=()):
	"""Desk and backfill only: the Customer that pays the order of ``buyer`` (an Attendee).

	Reuses the buyer's (or a group member's) Customer; else converts the buyer's Lead the ERPNext way
	(``customer_type`` Company with a company name, else Individual; Contacts and Address of the Lead move
	to the Customer and the Lead becomes Converted).
	"""
	for row in (buyer, *group):
		if row.customer:
			return row.customer
	if not buyer.lead:
		link_attendee(buyer)
		buyer.reload()
		if buyer.customer:
			return buyer.customer
	from erpnext.crm.doctype.lead.lead import _make_customer

	existing = frappe.db.get_value("Customer", {"lead_name": buyer.lead})
	if existing:
		return existing
	customer = _make_customer(buyer.lead, ignore_permissions=False)
	customer.customer_name = buyer.company_name or buyer.full_name
	customer.customer_type = "Company" if buyer.company_name else "Individual"
	customer.insert()
	return customer.name
