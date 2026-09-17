# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Read a Lead's correspondence with Mistral and propose people worth adding as Contacts.

Runs only when a user asks for it from the cockpit — there's no hook and no
scheduled job. Email bodies are personal data and every call costs money, so
this stays an explicit action rather than something that happens to every
message that arrives.
"""

import json
import re

import frappe
from frappe import _

from frappe.utils.html_utils import unescape_html

from phamos.api.sales_leads import (
	_check_lead_access,
	_lead_communications,
	_linked_contact_names,
)
from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings
from phamos.phamos.hr.interview_summary import _call_mistral_chat

# Enough correspondence to see a signature block or two, without sending a
# whole mailbox to a third party.
MAX_MESSAGES = 15
MAX_BODY_CHARS = 4000
MAX_PROMPT_CHARS = 20000

PROMPT = """You are reading email correspondence about a single sales lead.

Identify the PEOPLE who appear in it — typically from signature blocks, from
introductions ("my colleague X will take over"), and from sender and recipient
addresses. For each person return what the correspondence actually says; never
invent a detail that is not there.

Return ONLY a JSON object of this shape:
{{"people": [{{"first_name": "", "last_name": "", "email": "", "phone": "",
"designation": "", "company_name": "", "evidence": ""}}]}}

Rules:
- "evidence" is a short quote or paraphrase from the correspondence saying why
  you believe this person exists and holds that role. Keep it under 20 words.
- Leave a field as an empty string when the correspondence does not say.
- Skip automated senders (no-reply, mailer-daemon, calendar notifications,
  ticket systems) and mailing lists.
- Skip anyone whose address is at these domains, they are our own staff: {own_domains}
- One entry per person, not per message.

Correspondence:
{correspondence}
"""


def _strip_html(value):
	text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", value or "", flags=re.S | re.I)
	text = re.sub(r"<[^>]+>", " ", text)
	text = unescape_html(text)
	return re.sub(r"[ \t]*\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def _own_domains():
	"""Domains that are us, so our own people aren't proposed as lead contacts."""
	domains = set()
	for email in frappe.get_all(
		"Email Account", filters={"enable_outgoing": 1}, pluck="email_id"
	):
		if email and "@" in email:
			domains.add(email.split("@")[-1].strip().casefold())

	owner = frappe.session.user
	if owner and "@" in owner and owner != "Administrator":
		domains.add(owner.split("@")[-1].strip().casefold())
	return sorted(d for d in domains if d)


def _known_addresses(lead, lead_doc):
	"""Addresses already on the lead or one of its contacts."""
	known = set()
	if lead_doc.email_id:
		known.add(lead_doc.email_id.strip().casefold())

	contact_names = _linked_contact_names(lead)
	if contact_names:
		for row in frappe.get_all(
			"Contact", filters={"name": ("in", contact_names)}, fields=["email_id"]
		):
			if row.email_id:
				known.add(row.email_id.strip().casefold())
		for row in frappe.get_all(
			"Contact Email", filters={"parent": ("in", contact_names)}, fields=["email_id"]
		):
			if row.email_id:
				known.add(row.email_id.strip().casefold())
	return known


def _correspondence_text(lead):
	messages = _lead_communications(
		lead,
		fields=[
			"name",
			"subject",
			"content",
			"sender",
			"recipients",
			"cc",
			"communication_date",
			"sent_or_received",
		],
		limit=MAX_MESSAGES,
	)

	blocks = []
	for message in messages:
		body = _strip_html(message.get("content"))[:MAX_BODY_CHARS]
		blocks.append(
			"\n".join(
				filter(
					None,
					[
						f"--- {message.get('sent_or_received') or ''} {message.get('communication_date') or ''}",
						f"From: {message.get('sender') or ''}",
						f"To: {message.get('recipients') or ''}",
						f"Cc: {message.get('cc')}" if message.get("cc") else "",
						f"Subject: {message.get('subject') or ''}",
						"",
						body,
					],
				)
			)
		)

	return "\n\n".join(blocks)[:MAX_PROMPT_CHARS], len(messages)


def _parse_people(raw):
	"""Mistral is asked for a JSON object but sometimes wraps it in prose."""
	text = (raw or "").strip()
	if text.startswith("```"):
		text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.I)
	try:
		data = json.loads(text)
	except ValueError:
		match = re.search(r"\{.*\}", text, flags=re.S)
		if not match:
			return []
		try:
			data = json.loads(match.group(0))
		except ValueError:
			return []

	people = data.get("people") if isinstance(data, dict) else data
	return people if isinstance(people, list) else []


@frappe.whitelist(methods=["POST"])
def suggest_contacts_from_email(lead):
	"""Propose people found in this Lead's correspondence, for the user to accept."""
	_check_lead_access()
	frappe.has_permission("Lead", "write", throw=True)
	frappe.has_permission("Contact", "create", throw=True)

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	settings = _get_phamos_settings()
	if not settings:
		frappe.throw(_("Mistral is not configured in phamos Settings."))

	correspondence, message_count = _correspondence_text(lead)
	if not correspondence.strip():
		return {"suggestions": [], "message_count": 0}

	own_domains = _own_domains()
	raw = _call_mistral_chat(
		settings,
		PROMPT.format(own_domains=", ".join(own_domains) or "none", correspondence=correspondence),
	)

	known = _known_addresses(lead, lead_doc)
	suggestions = []
	seen = set()
	for person in _parse_people(raw):
		if not isinstance(person, dict):
			continue
		email = (person.get("email") or "").strip()
		key = email.casefold() or (
			f"{person.get('first_name', '')} {person.get('last_name', '')}".strip().casefold()
		)
		# Nothing to identify the person by, already on file, one of ours, or a
		# duplicate of an earlier entry.
		if not key or key in seen or key in known:
			continue
		if email and email.split("@")[-1].strip().casefold() in own_domains:
			continue
		seen.add(key)
		suggestions.append(
			{
				"first_name": (person.get("first_name") or "").strip(),
				"last_name": (person.get("last_name") or "").strip(),
				"email": email,
				"phone": (person.get("phone") or "").strip(),
				"designation": (person.get("designation") or "").strip(),
				"company_name": (person.get("company_name") or "").strip()
				or (lead_doc.company_name or ""),
				"evidence": (person.get("evidence") or "").strip(),
			}
		)

	return {"suggestions": suggestions, "message_count": message_count}


@frappe.whitelist(methods=["POST"])
def create_lead_contact(
	lead, first_name=None, last_name=None, email=None, phone=None, designation=None, company_name=None
):
	"""Save an accepted suggestion as a Contact linked to this Lead."""
	_check_lead_access()
	frappe.has_permission("Lead", "write", throw=True)
	frappe.has_permission("Contact", "create", throw=True)

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	first_name = (first_name or "").strip()
	email = (email or "").strip()
	if not first_name and not email:
		frappe.throw(_("A contact needs at least a name or an email address."))

	# These values started life as model output derived from untrusted email,
	# so they are validated here rather than trusted because the dialog sent
	# them: a crafted mail can talk the model into proposing a plausible name
	# against an address the attacker controls.
	if email:
		frappe.utils.validate_email_address(email, throw=True)

	contact = frappe.new_doc("Contact")
	contact.first_name = first_name or email.split("@")[0]
	contact.last_name = (last_name or "").strip()
	contact.designation = (designation or "").strip()
	contact.company_name = (company_name or "").strip() or lead_doc.company_name
	if email:
		contact.append("email_ids", {"email_id": email, "is_primary": 1})
	if (phone or "").strip():
		contact.append("phone_nos", {"phone": phone.strip(), "is_primary_mobile_no": 1})
	contact.append(
		"links", {"link_doctype": "Lead", "link_name": lead_doc.name, "link_title": lead_doc.lead_name}
	)
	contact.insert()

	return {"name": contact.name}
