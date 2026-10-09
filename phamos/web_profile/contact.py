"""One contact workflow behind every "contact" button on the Web Profile pages.

The visitor always fills in the same dialog (name, email, optional phone, message). What happens
next depends on who they contact:

- a phamos person, or a page-level button ("Talk to us about this module"): the ERPNext
  /contact concept. The visitor becomes a Lead (or is matched to an existing Customer by email)
  and an Opportunity is created with the message as Communication, owned by and assigned to the
  phamos person when they have a user account.
- an external person (customer, supplier, partner) who consented to be contacted: the message is
  recorded on their Person Web Profile and forwarded to them by email. Their address never
  reaches the page.

Guests are rate-limited per IP; a hidden honeypot field catches simple bots.
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import escape_html, validate_email_address

from phamos.web_profile.sections import SECTIONS, find_item, key_people

MAX_MESSAGE = 4000
PHONE = re.compile(r"[0-9 +()./-]{5,40}")


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=5, seconds=60 * 60)
def submit(section, slug, lang, sender_name, sender_email, message, phone=None, privacy_consent=None, website=None):
	if website:
		# Honeypot: hidden from people, filled in by bots. Pretend success.
		return {"ok": True}

	lang = lang if lang in ("de", "en") else "en"
	sender_name = (sender_name or "").strip()[:140]
	sender_email = (sender_email or "").strip()[:140]
	phone = (phone or "").strip()[:40]
	message = (message or "").strip()
	if not sender_name or not message:
		frappe.throw(_("Please enter your name and a message."))
	if not validate_email_address(sender_email):
		frappe.throw(_("Please enter a valid email address."))
	if phone and not PHONE.fullmatch(phone):
		frappe.throw(_("Please enter a valid phone number or leave it empty."))
	if len(message) > MAX_MESSAGE:
		frappe.throw(_("Please keep your message under {0} characters.").format(MAX_MESSAGE))
	if not frappe.utils.cint(privacy_consent):
		frappe.throw(_("Please agree that we pass your message on."))

	if section == "contact":
		# General contact (e.g. the contact Web Page): goes to the sales contact (Web Profile Settings).
		item = frappe._dict(section="contact", title=_("Contact"), url=f"/{lang}/{'kontakt' if lang == 'de' else 'contact'}",
			data={})
		person = _sales_contact(lang)
		_create_opportunity(item, person, frappe._dict(name=sender_name, email=sender_email, phone=phone, message=message))
		return {"ok": True, "flow": "opportunity"}

	item, _gone = find_item(section, slug, lang) if section in SECTIONS else (None, False)
	if not item:
		frappe.throw(_("This page can't be contacted through the website."), frappe.PermissionError)

	if section == "people" and item.masked:
		# An anonymous person can't be contacted, not even through phamos (phamos/phamos#1509).
		frappe.throw(_("This person can't be contacted through the website."), frappe.PermissionError)

	visitor = frappe._dict(name=sender_name, email=sender_email, phone=phone, message=message)
	person = item if section == "people" else None
	if person and person.data["party_type"] != "Employee":
		if not person.data.get("contactable"):
			frappe.throw(_("This person can't be contacted through the website."), frappe.PermissionError)
		_relay_to_external(person, visitor)
		return {"ok": True, "flow": "relay"}

	if person and not person.data.get("contactable"):
		person = None  # e.g. alumni: the request goes to phamos in general
	if not person:
		# Page-level request: route it to the page's phamos key person, if there is one.
		person = next((c["person"] for c in key_people(item, lang)
			if c["person"].data["party_type"] == "Employee" and c["person"].data.get("contactable")), None)
	_create_opportunity(item, person, visitor)
	return {"ok": True, "flow": "opportunity"}


def _sales_contact(lang):
	from phamos.web_profile.sections import _person_by_name

	settings = frappe.db.get_singles_dict("Web Profile Settings")
	person = _person_by_name(settings.get("sales_contact"), lang)
	return person if person and person.data.get("contactable") else None


# --- phamos people and pages: Lead / Customer + Opportunity ----------------------------------------


def _create_opportunity(item, person, visitor):
	"""Same idea as ERPNext's /contact form (erpnext.templates.utils.send_message), plus phone,
	the page the request came from and the phamos person it was addressed to."""
	source = "Website" if frappe.db.exists("Lead Source", "Website") else None
	customer = frappe.db.sql(
		"""select distinct dl.link_name from `tabDynamic Link` dl
		join `tabContact` c on dl.parent = c.name
		where dl.parenttype = 'Contact' and dl.link_doctype = 'Customer' and c.email_id = %s""",
		visitor.email,
	)
	if customer:
		party_type, party = "Customer", customer[0][0]
	else:
		party_type = "Lead"
		party = frappe.db.get_value("Lead", {"email_id": visitor.email})
		if not party:
			first_name, _sep, last_name = visitor.name.partition(" ")
			lead = frappe.get_doc({
				"doctype": "Lead", "first_name": first_name, "last_name": last_name, "lead_name": visitor.name,
				"email_id": visitor.email, "mobile_no": visitor.phone or None, "status": "Lead", "source": source,
			})
			lead.insert(ignore_permissions=True)
			party = lead.name
		elif visitor.phone and not frappe.db.get_value("Lead", party, "mobile_no"):
			frappe.db.set_value("Lead", party, "mobile_no", visitor.phone)

	owner = frappe.db.get_value("Employee", person.data["party"], "user_id") if person else None
	# "Website: Roque Vera" for a person, "Website: Accounting · Furqan Asghar" for a page.
	about = item.title if item.section != "people" else None
	subject = _("Website: {0}").format(" · ".join(filter(None, [about, person.title if person else None])) or item.title)
	opportunity = frappe.get_doc({
		"doctype": "Opportunity",
		"opportunity_from": party_type,
		"party_name": party,
		"status": "Open",
		"title": subject,
		"contact_email": visitor.email,
		"contact_mobile": visitor.phone or None,
		"opportunity_owner": owner,
		"source": source,
	})
	opportunity.insert(ignore_permissions=True)
	_record(visitor, subject, "Opportunity", opportunity.name, _content(item, visitor, person))

	if owner:
		from frappe.desk.form.assign_to import add as assign

		try:
			assign({"assign_to": [owner], "doctype": "Opportunity", "name": opportunity.name,
				"description": subject}, ignore_permissions=True)
		except Exception:
			frappe.log_error(title="Web Profile contact: assignment failed", reference_doctype="Opportunity",
				reference_name=opportunity.name)
	return opportunity.name


# --- external people: record + forward by email ------------------------------------------------------


def _relay_to_external(person, visitor):
	recipient = frappe.db.get_value("Person Web Profile", person.name, "email_id")
	subject = _("Message from {0} via phamos.eu").format(visitor.name)
	html = _content(person, visitor, person, forwarded=True)
	# Recorded first, on the profile's timeline, so no message is lost if forwarding fails.
	_record(visitor, subject, "Person Web Profile", person.name, html)
	try:
		frappe.sendmail(recipients=[recipient], reply_to=visitor.email, subject=subject, message=html,
			reference_doctype="Person Web Profile", reference_name=person.name)
	except frappe.OutgoingEmailError:
		frappe.clear_messages()  # the visitor needn't see phamos' mail setup; the message is recorded
		frappe.log_error(title="Web Profile contact form: email not forwarded",
			reference_doctype="Person Web Profile", reference_name=person.name)


# --- shared ---------------------------------------------------------------------------------------------


def _record(visitor, subject, reference_doctype, reference_name, html):
	frappe.get_doc({
		"doctype": "Communication",
		"communication_type": "Communication",
		"communication_medium": "Email",
		"sent_or_received": "Received",
		"subject": subject,
		"content": html,
		"sender": visitor.email,
		"sender_full_name": visitor.name,
		"phone_no": visitor.phone or None,
		"reference_doctype": reference_doctype,
		"reference_name": reference_name,
	}).insert(ignore_permissions=True)


def _content(item, visitor, person, forwarded=False):
	esc = escape_html
	intro = (_("{0} wrote to you through your profile on phamos.eu:").format(visitor.name) if forwarded
		else _("Request from the website page {0}:").format(item.title))
	details = filter(None, [
		_("Name: {0}").format(visitor.name),
		_("Email: {0}").format(visitor.email),
		_("Phone: {0}").format(visitor.phone) if visitor.phone else None,
		_("Addressed to: {0}").format(person.title) if person and not forwarded else None,
		_("Page: {0}").format(frappe.utils.get_url(item.url)),
	])
	html = (
		f"<p>{esc(intro)}</p>"
		f"<blockquote>{esc(visitor.message).replace(chr(10), '<br>')}</blockquote>"
		f"<p>{'<br>'.join(esc(line) for line in details)}</p>"
	)
	if forwarded:
		html += "<p><small>" + esc(_("Reply to this email to answer {0} directly. You receive this because you agreed to be contactable via your profile on phamos.eu.").format(visitor.name)) + "</small></p>"
	return html
