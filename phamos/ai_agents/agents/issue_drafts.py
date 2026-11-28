# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue Assistant, e-mail drafts to the reporter (#2229).

On request in the Issue chat (#2116) the assistant writes an e-mail draft to the reporter. A person
reviews it on the Issue and sends it; nothing goes out by itself (#1953 decision 4).

The draft is a Communication marked `custom_draft`. It is **not linked to the Issue while it is a
draft** (`custom_draft_issue` holds the Issue): a Communication linked to an Issue counts as a sent
reply as soon as it is saved (Frappe's first response time, ERPNext's SLA), and it would show in the
Issue's timeline as an e-mail.

The chat's link opens the Issue with Frappe's usual e-mail dialog, filled from the draft (PM's local
test 2026-11-28). It sends a new e-mail the standard way; the draft is deleted afterwards. Staff can't
open a Communication in Desk (write: System Manager only), so drafts are read and discarded through
the endpoints below, which check the Issue's permissions.

A check in code warns, without blocking, when the e-mail names another customer, contains another
customer's e-mail domain, address or phone number, or goes to a recipient outside this Issue's
customer (#1953 confidentiality; warn only, PM 2026-11-28).
"""

import re

import frappe
from frappe import _
from frappe.utils import cstr, escape_html, get_url, strip_html_tags, validate_email_address

DRAFT_FIELD = "custom_draft"
ISSUE_FIELD = "custom_draft_issue"
RUN_FIELD = "custom_ai_agent_run"
# addresses at these domains say nothing about a customer: never treated as another customer's domain
COMMON_DOMAINS = {
	"gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "gmx.de", "gmx.net",
	"web.de", "t-online.de", "icloud.com", "me.com", "posteo.de", "mailbox.org", "example.com",
}
MIN_NAME_LENGTH = 4
MIN_PHONE_DIGITS = 7


# --- creating (from the chat) --------------------------------------------------------------------


def reporter_email(issue):
	"""The address the reply goes to: the Issue's sender, else its Contact's primary e-mail."""
	email = cstr(issue.get("raised_by")).strip()
	if not email and issue.get("contact"):
		email = frappe.db.get_value("Contact", issue.contact, "email_id")
	return email or None


def reporter_language(issue):
	"""The reporter's language: their User's, else the site's (German for phamos)."""
	email = reporter_email(issue)
	user = email and frappe.db.get_value("User", {"email": email}, "language")
	return user or frappe.db.get_single_value("System Settings", "language") or "de"


def create_draft(issue, subject, body, run=None):
	"""A draft Communication for the Issue's reporter. Returns its name, or raises when there is no
	reporter address. Inserted without permission checks: callers check the Issue (#2116 runs it for
	an asker who may write the Issue)."""
	to = reporter_email(issue)
	if not to:
		frappe.throw(_("The Issue has no reporter e-mail address to write to."))
	content = "".join(f"<p>{escape_html(line)}</p>" for line in cstr(body).split("\n") if line.strip())
	comm = frappe.get_doc({
		"doctype": "Communication",
		"communication_type": "Communication",
		# not "Email" yet: Frappe would add timeline links to the recipients' Contacts and Customer
		"communication_medium": "Other",
		"sent_or_received": "Sent",
		"subject": cstr(subject).strip()[:140] or issue.subject,
		"content": content,
		"recipients": to,
		DRAFT_FIELD: 1,
		ISSUE_FIELD: issue.name,
		RUN_FIELD: run,
	})
	comm.flags.skip_add_signature = True  # the sender's signature comes with Send
	comm.insert(ignore_permissions=True)
	return comm.name


def draft_url(issue_name, draft):
	return get_url(f"/app/issue/{issue_name}?draft={draft}")


# --- reading and discarding (Issue form) --------------------------------------------------------


def _draft(name, ptype):
	"""The draft and its Issue, after checking the Issue's permission."""
	row = frappe.db.get_value("Communication", name, ["name", DRAFT_FIELD, ISSUE_FIELD], as_dict=True)
	if not row or not row.get(DRAFT_FIELD) or not row.get(ISSUE_FIELD):
		frappe.throw(_("E-mail draft {0} not found.").format(name), frappe.DoesNotExistError)
	issue = frappe.get_doc("Issue", row.get(ISSUE_FIELD))
	issue.check_permission(ptype)
	return frappe.get_doc("Communication", name), issue


def _as_dict(comm):
	return {"name": comm.name, "subject": comm.subject, "content": comm.content, "recipients": comm.recipients,
		"cc": comm.cc, "creation": comm.creation, "issue": comm.get(ISSUE_FIELD)}


@frappe.whitelist()
def get_drafts(issue):
	"""Open e-mail drafts of an Issue, for whoever may read it."""
	frappe.get_doc("Issue", issue).check_permission("read")
	names = frappe.get_all("Communication", filters={ISSUE_FIELD: issue, DRAFT_FIELD: 1}, pluck="name",
		order_by="creation desc")
	return [_as_dict(frappe.get_doc("Communication", n)) for n in names]


@frappe.whitelist(methods=["POST"])
def discard_draft(name):
	comm, issue = _draft(name, "write")
	frappe.delete_doc("Communication", comm.name, ignore_permissions=True)
	return {"name": name, "discarded": 1}


# --- the check --------------------------------------------------------------------------


def _emails(text):
	return [e.strip().lower() for e in re.split(r"[,;\n]", cstr(text)) if e.strip()]


def _digits(text):
	return re.sub(r"\D", "", cstr(text))


def confidentiality_problems(comm, issue):
	"""What speaks against this e-mail going to this Issue's customer: [message], empty when nothing."""
	from phamos.ai_agents.agents.issue import customer_of

	customer = customer_of(issue)
	text = f"{comm.subject}\n{strip_html_tags(cstr(comm.content))}"
	lowered = text.lower()
	problems = []

	others = frappe.get_all("Customer", filters={"name": ("!=", customer or "")}, fields=["name", "customer_name"])
	for row in others:
		for name in {row.customer_name, row.name}:
			if name and len(name) >= MIN_NAME_LENGTH and re.search(rf"(?<!\w){re.escape(name.lower())}(?!\w)", lowered):
				problems.append(_("It names another customer: {0}").format(name))
				break

	own = _customer_emails(customer) if customer else set()
	other_emails = _other_customer_emails(customer)
	own_domains = {e.split("@")[-1] for e in own}
	for email in sorted(other_emails):
		domain = email.split("@")[-1]
		if email in lowered:
			problems.append(_("It contains another customer's e-mail address: {0}").format(email))
		elif domain not in COMMON_DOMAINS and domain not in own_domains and re.search(
				rf"(?<![\w.-]){re.escape(domain)}(?!\w)", lowered):
			problems.append(_("It contains another customer's domain: {0}").format(domain))
	text_digits = _digits(text)
	for phone in _other_customer_phones(customer):
		if len(phone) >= MIN_PHONE_DIGITS and phone in text_digits:
			problems.append(_("It contains another party's phone number."))
			break

	allowed = own | {cstr(reporter_email(issue)).lower()}
	for email in _emails(comm.recipients) + _emails(comm.cc):
		if not validate_email_address(email):
			problems.append(_("Not an e-mail address: {0}").format(email))
		elif email not in allowed:
			problems.append(_("Recipient {0} is not a contact of this Issue's customer.").format(email))
	return list(dict.fromkeys(problems))


def _contacts_of(customer, exclude=False):
	filters = {"parenttype": "Contact", "link_doctype": "Customer"}
	filters["link_name"] = ("!=", customer or "") if exclude else customer
	return frappe.get_all("Dynamic Link", filters=filters, pluck="parent", distinct=True)


def _customer_emails(customer):
	contacts = _contacts_of(customer)
	return {e.lower() for e in frappe.get_all("Contact Email", filters={"parent": ("in", contacts or [""])},
		pluck="email_id") if e}


def _other_customer_emails(customer):
	contacts = _contacts_of(customer, exclude=True)
	own = set(_contacts_of(customer)) if customer else set()
	contacts = [c for c in contacts if c not in own]
	return {e.lower() for e in frappe.get_all("Contact Email", filters={"parent": ("in", contacts or [""])},
		pluck="email_id") if e}


def _other_customer_phones(customer):
	contacts = _contacts_of(customer, exclude=True)
	own = set(_contacts_of(customer)) if customer else set()
	contacts = [c for c in contacts if c not in own]
	return {_digits(p) for p in frappe.get_all("Contact Phone", filters={"parent": ("in", contacts or [""])},
		pluck="phone") if p}


@frappe.whitelist(methods=["POST"])
def check_email(issue, subject=None, content=None, recipients=None, cc=None):
	"""Warnings for an e-mail on this Issue as written in the e-mail dialog: [message], empty when fine."""
	doc = frappe.get_doc("Issue", issue)
	doc.check_permission("read")
	return confidentiality_problems(frappe._dict(subject=subject, content=content, recipients=recipients, cc=cc), doc)
