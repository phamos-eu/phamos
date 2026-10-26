"""Who is this person in our CRM? Contact, Lead and Customer for attendees and buyers.

Rules (phamos/phamos#1169):

1. A Contact with the email exists: use it; if it is linked to exactly one Customer, that is the party.
2. Else a Lead with the email exists: reuse it (a Converted Lead brings its Customer).
3. Else, when allowed, create a Lead (source "Event", the event's Campaign) and its Contact.

``resolve_party`` never creates a Customer. A company name that matches a Customer without an email link is only a hint (``crm_status`` "Needs
Review"): a person decides, so no wrong Customer is reused.

Rules 1 and 2 apply to verified emails only (Desk, ``link_attendee``).

Everything that comes in from the website (the contact form and every event order, free or paid) follows one
process instead, ``match_or_create_lead`` (phamos/phamos#1724): the Customer of a Contact with that email, else
the Lead with that email, else a new Lead owned by "Guest". The website only links people; Customer, Address
and Sales Order are created in the desk (phamos/phamos#1725), where a person confirms them. That is also why
a website link may reuse an existing record: nothing of it is shown to the visitor.
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


def customer_for_email(email):
	"""The Customer of a Contact with this email (in the Contact or its email rows), or None."""
	customers = customers_for_email(email)
	return customers[0] if customers else None


def customers_for_email(email):
	"""All Customers of Contacts with this email, sorted by name."""
	if not email:
		return []
	contact, email_row, link = frappe.qb.DocType("Contact"), frappe.qb.DocType("Contact Email"), frappe.qb.DocType("Dynamic Link")
	rows = (frappe.qb.from_(link).join(contact).on(link.parent == contact.name)
		.left_join(email_row).on((email_row.parent == contact.name) & (email_row.parenttype == "Contact"))
		.select(link.link_name).distinct()
		.where((link.parenttype == "Contact") & (link.link_doctype == "Customer")
			& ((contact.email_id == email) | (email_row.email_id == email)))
		.orderby(link.link_name).run())
	return [row[0] for row in rows]


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
		# Infrastructure record, created once for everybody: no user permission involved.
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
		campaign.insert(ignore_permissions=True)  # infrastructure record, one per event
		name = campaign.name
	frappe.db.set_value("Marketing Content", event_doc.name, "campaign", name, update_modified=False)
	event_doc.campaign = name
	return name


# ``ignore_permissions`` in the helpers below: False by default, so desk actions run with the user's own
# rights (phamos/phamos#1709); only the website's own step, ``match_or_create_lead``, ignores them.


def create_lead(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		campaign=None, ignore_permissions=False, lead_owner=None, source=None):
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
		"source": source or ensure_lead_source(),
		"campaign_name": campaign,
		# None: ERPNext's default, the current user. The website passes WEBSITE_LEAD_OWNER.
		**({"lead_owner": lead_owner} if lead_owner else {}),
	})
	lead.insert(ignore_permissions=ignore_permissions)
	return lead.name


# Leads from the website are owned by "Guest": the Lead Assignment Rule ("Based on Field lead_owner",
# condition lead_owner != "Guest") leaves them alone, as it always did for the contact form (phamos/phamos#1718).
WEBSITE_LEAD_OWNER = "Guest"


def match_or_create_lead(*, email, first_name, last_name="", company_name="", phone="", campaign=None, source=None):
	"""The one CRM step for everything that comes in from the website (phamos/phamos#1724).

	1. The email belongs to a Contact of a Customer: that Customer (and the Contact).
	2. Else a Lead with that email: that Lead (and its Contact, if any); a missing phone is filled in.
	3. Else a new Lead owned by "Guest" (and the Contact ERPNext may create for it).

	Returns {customer, lead, contact, created}. Runs in the visitor's session, so it ignores permissions.
	"""
	email = normalize_email(email, throw=False)
	result = frappe._dict(customer=None, lead=None, contact=None, created=False)
	if not email:
		return result
	result.contact = contact_for_email(email)
	result.customer = customer_for_email(email)
	if result.customer:
		return result
	result.lead = lead_for_email(email)
	if result.lead:
		if phone and not frappe.db.get_value("Lead", result.lead, "mobile_no"):
			frappe.db.set_value("Lead", result.lead, "mobile_no", phone)
		return result
	result.lead = create_lead(email=email, first_name=first_name, last_name=last_name, company_name=company_name,
		phone=phone, campaign=campaign, source=source, ignore_permissions=True, lead_owner=WEBSITE_LEAD_OWNER)
	result.created = True
	# ERPNext may have created the Lead's Contact (CRM Settings "Auto Creation of Contact").
	result.contact = result.contact or contact_for_email(email)
	return result


def create_contact(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		links=(), ignore_permissions=False):
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
	contact.insert(ignore_permissions=ignore_permissions)
	return contact.name


def ensure_contact_links(contact, links, ignore_permissions=False):
	"""Add missing Dynamic Links (doctype, name) to a Contact."""
	if not contact:
		return
	doc = frappe.get_doc("Contact", contact)
	existing = {(row.link_doctype, row.link_name) for row in doc.links}
	missing = [(dt, name) for dt, name in links if name and (dt, name) not in existing]
	for doctype, name in missing:
		doc.append("links", {"link_doctype": doctype, "link_name": name})
	if missing:
		doc.save(ignore_permissions=ignore_permissions)


def create_address(*, title, address_line1, city, country, pincode="", address_line2="", email="", phone="",
		links=(), ignore_permissions=False):
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
	address.insert(ignore_permissions=ignore_permissions)
	return address.name


def resolve_party(*, email, first_name, last_name="", company_name="", phone="", job_title="", salutation="",
		event=None, create=True, link_to_lead=None, link_to_customer=None, verified=True, ignore_permissions=False,
		lead_owner=None):
	"""Contact + Lead or Customer for one person (rules in the module docstring).

	``link_to_customer``: the buying company for companions of a company order: their Contact is linked to
	that Customer and they get no Lead of their own. ``link_to_lead``: the same for a buyer who is a Lead.
	``verified``: False for email addresses typed on the website; then existing records are only reported
	(``review_note``), never reused or changed.
	"""
	found = find_party(email, company_name)
	if not verified and (found.contact or found.lead or found.customers):
		return frappe._dict(contact=None, lead=None, customer=link_to_customer, created=[], crm_status="Needs Review",
			suggestions=found.suggestions, review_note=_review_note(found))
	result = frappe._dict(contact=found.contact, lead=found.lead, customer=found.customer, created=[],
		crm_status="Linked" if found.confidence == "strong" else "Needs Review" if found.confidence == "review"
		else "Unlinked", suggestions=found.suggestions, review_note=None)
	if not create:
		if found.contact or found.lead:
			result.crm_status = result.crm_status if result.crm_status != "Unlinked" else "Linked"
		return result

	person = dict(email=found.email, first_name=first_name, last_name=last_name, company_name=company_name,
		phone=phone, job_title=job_title, salutation=salutation)
	campaign = get_or_create_campaign(event) if event is not None else None

	if link_to_customer and not result.customer:
		result.customer = link_to_customer
	if not result.customer and not result.lead and not link_to_lead:
		result.lead = create_lead(campaign=campaign, ignore_permissions=ignore_permissions, lead_owner=lead_owner,
			**person)
		result.created.append(("Lead", result.lead))
		# ERPNext may have created the Lead's Contact (CRM Settings "Auto Creation of Contact").
		result.contact = result.contact or contact_for_email(found.email)
	elif result.lead and company_name and not frappe.db.get_value("Lead", result.lead, "company_name"):
		frappe.db.set_value("Lead", result.lead, "company_name", company_name)

	links = [("Customer", result.customer)] if result.customer else [("Lead", result.lead or link_to_lead)]
	if not result.contact:
		result.contact = create_contact(links=links, ignore_permissions=ignore_permissions, **person)
		result.created.append(("Contact", result.contact))
	else:
		ensure_contact_links(result.contact, links, ignore_permissions=ignore_permissions)

	if result.crm_status == "Unlinked":
		result.crm_status = "Linked"
	return result


def _review_note(found):
	"""What a website order's email matches in the CRM, for the person who links it."""
	parts = [f"{_('Contact')} {found.contact}" if found.contact else None,
		f"{_('Lead')} {found.lead}" if found.lead else None,
		*(f"{_('Customer')} {c}" for c in found.customers or [])]
	return _("Possible match: {0}. Not linked automatically: the email address of a website order is not "
		"verified. Check it, then use \"Link to CRM\".").format(", ".join(filter(None, parts)))


def link_attendee(attendee, create=True, ignore_permissions=False):
	"""Resolve one Attendee and store contact / lead / customer / crm_status on it."""
	doc = frappe.get_doc("Attendee", attendee) if isinstance(attendee, str) else attendee
	event = frappe.get_doc("Marketing Content", doc.event)
	result = resolve_party(email=doc.email, first_name=doc.first_name, last_name=doc.last_name,
		company_name=doc.company_name, phone=doc.phone, job_title=doc.job_title, salutation=doc.salutation,
		event=event, create=create, ignore_permissions=ignore_permissions)
	values = {"contact": result.contact, "lead": result.lead, "customer": result.customer,
		"crm_status": result.crm_status}
	frappe.db.set_value("Attendee", doc.name, values)
	return {**values, "attendee": doc.name, "created": result.created, "suggestions": result.suggestions}


def ensure_customer_for_order(buyer, group=(), ignore_permissions=False):
	"""Desk and backfill only: the Customer that pays the order of ``buyer`` (an Attendee).

	Reuses the buyer's (or a group member's) Customer; else converts the buyer's Lead the ERPNext way
	(``customer_type`` Company with a company name, else Individual; Contacts and Address of the Lead move
	to the Customer and the Lead becomes Converted).
	"""
	for row in (buyer, *group):
		if row.customer:
			return row.customer
	if not buyer.lead:
		link_attendee(buyer, ignore_permissions=ignore_permissions)
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


def _leaf(doctype, preferred):
	"""``preferred`` when it is a leaf (ERPNext refuses group nodes), else the first leaf."""
	if preferred and not frappe.db.get_value(doctype, preferred, "is_group"):
		return preferred
	return frappe.db.get_value(doctype, {"is_group": 0}, "name", order_by="lft asc")



# --- desk: the Customer of an Event Ticket Order (phamos/phamos#1725) ------------------------------------
# Everything below runs with the desk user's own rights: a person chose the Customer in the dialog.


def order_customer_proposal(order):
	"""What "Create Sales Order" proposes for an Event Ticket Order, following the buyer's link (#1724).

	``action``: "use" (the buyer is linked to a Customer, directly or through a converted Lead), "convert" (the
	buyer is linked to a Lead: convert it) or "choose" (neither: a person chooses). ``unambiguous`` lets the bulk
	action go ahead without asking: the buyer's email belongs to exactly one Customer, or the buyer is a Lead
	whose company name matches no Customer (``matches``).
	"""
	lead_customer = order.lead and (frappe.db.get_value("Lead", order.lead, "customer")
		or frappe.db.get_value("Customer", {"lead_name": order.lead}, "name"))
	customer = order.customer or lead_customer
	company = _order_company(order) or (order.lead and frappe.db.get_value("Lead", order.lead, "company_name"))
	matches = suggest_customer_for_company(company) if company and not customer else []
	if customer:
		action = "use"
		unambiguous = bool(lead_customer) or len(customers_for_email(order.buyer_email)) <= 1
	elif order.lead:
		action, unambiguous = "convert", not matches
	else:
		action, unambiguous = "choose", False
	return frappe._dict(action=action, customer=customer, lead=order.lead, matches=matches, unambiguous=unambiguous)


def customer_for_order(order, mode, customer=None):
	"""The Customer that pays an Event Ticket Order.

	``mode``: "use" an existing ``customer`` (the buyer's Lead, if any, is linked to it and Converted),
	"convert" the buyer's Lead the ERPNext way (its Contacts and Addresses move to the new Customer), or "new":
	a Customer from the billing data, the buyer's Contact linked to it as well.
	"""
	if mode == "use":
		if not customer:
			frappe.throw(_("Please choose a Customer."))
		if order.lead:
			_link_lead(order.lead, customer)
		return customer
	if mode == "convert":
		if not order.lead:
			frappe.throw(_("The buyer of {0} is not linked to a Lead.").format(order.name))
		return convert_lead(order.lead, _order_customer_name(order), _order_customer_type(order), order.billing_vat_id,
			order.language)
	if mode == "new":
		settings = frappe.db.get_singles_dict("Selling Settings")
		doc = frappe.get_doc({
			"doctype": "Customer",
			"customer_name": _order_customer_name(order),
			"customer_type": _order_customer_type(order),
			"customer_group": _leaf("Customer Group", settings.get("customer_group")),
			"territory": _leaf("Territory", settings.get("territory")),
			"tax_id": order.billing_vat_id or None,
			"language": order.language or None,
		}).insert()
		return doc.name
	frappe.throw(_("Unknown choice {0}.").format(mode))


def _order_company(order):
	return order.billing_company if order.billing_is_company else None


def _order_customer_type(order):
	return "Company" if _order_company(order) else "Individual"


def _order_customer_name(order):
	return (_order_company(order) or order.billing_name or order.buyer_name or order.buyer_email)[:140]


def convert_lead(lead, customer_name, customer_type, tax_id=None, language=None):
	"""ERPNext's Lead → Customer: the Customer gets ``lead_name``, on save ERPNext moves the Lead's Contacts and
	Addresses to it and sets the Lead to Converted. A Lead converted before keeps its Customer."""
	from erpnext.crm.doctype.lead.lead import _make_customer

	existing = frappe.db.get_value("Customer", {"lead_name": lead})
	if existing:
		return existing
	customer = _make_customer(lead)
	customer.customer_name, customer.customer_type = customer_name, customer_type
	customer.customer_group = _leaf("Customer Group", customer.customer_group)
	customer.territory = _leaf("Territory", customer.get("territory") or
		frappe.db.get_single_value("Selling Settings", "territory"))
	if tax_id:
		customer.tax_id = tax_id
	if language:
		customer.language = language
	customer.insert()
	return customer.name


def _link_lead(lead, customer):
	"""A Lead whose person buys for an existing Customer: linked to it and Converted, as ERPNext does on
	conversion. A Lead that already has a Customer is left alone."""
	if frappe.db.get_value("Lead", lead, "customer"):
		return
	frappe.has_permission("Lead", "write", lead, throw=True)
	frappe.db.set_value("Lead", lead, {"customer": customer, "status": "Converted"})


def apply_billing_to_customer(order, customer):
	"""The order's billing data on the chosen Customer. Returns (contact, address) for the Sales Order.

	- The buyer's Contact is linked to the Customer; a billing email other than the buyer's is added to it.
	- The billing Address is linked to the Customer, created only if it has no Address with the same street,
	  postcode and city.
	- The VAT ID is set only if the Customer has none; a different one is noted in a comment, never overwritten.
	"""
	contact = order.contact or contact_for_email(order.buyer_email)
	if contact:
		ensure_contact_links(contact, [("Customer", customer)])
		billing_email = normalize_email(order.billing_email, throw=False)
		if billing_email and billing_email != normalize_email(order.buyer_email, throw=False):
			doc = frappe.get_doc("Contact", contact)
			if billing_email not in {row.email_id for row in doc.email_ids}:
				doc.append("email_ids", {"email_id": billing_email})
				doc.save()
	address = None
	if order.billing_address_line1:
		address = _same_address(customer, order) or create_address(
			title=_order_customer_name(order),
			address_line1=order.billing_address_line1, address_line2=order.billing_address_line2,
			city=order.billing_city, pincode=order.billing_postcode, country=order.billing_country,
			email=order.billing_email, links=[("Customer", customer)])
	if order.billing_vat_id:
		tax_id = frappe.db.get_value("Customer", customer, "tax_id")
		doc = frappe.get_doc("Customer", customer)
		if not tax_id:
			doc.tax_id = order.billing_vat_id
			doc.save()
		elif tax_id.replace(" ", "").upper() != order.billing_vat_id.replace(" ", "").upper():
			doc.add_comment("Comment", _("Event Ticket Order {0} was ordered with the VAT ID {1}; the Customer keeps "
				"{2}.").format(order.name, order.billing_vat_id, tax_id))
	return contact, address


def _same_address(customer, order):
	"""An Address of the Customer with the order's street, postcode and city (case and spaces ignored)."""
	def key(*parts):
		return tuple(" ".join((p or "").lower().split()) for p in parts)

	wanted = key(order.billing_address_line1, order.billing_postcode, order.billing_city)
	names = frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": "Customer",
		"link_name": customer}, pluck="parent")
	for row in frappe.get_all("Address", filters={"name": ["in", names or [""]], "disabled": 0},
			fields=["name", "address_line1", "pincode", "city"]):
		if key(row.address_line1, row.pincode, row.city) == wanted:
			return row.name
	return None
