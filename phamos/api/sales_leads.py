# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Leads API — Follow Ups list, Lead detail, notes, activity, and pipeline KPIs."""

import ipaddress
import json
import re
import socket
from datetime import timedelta
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.utils import get_datetime, getdate, now_datetime
from frappe.utils.html_utils import clean_email_html

from phamos.api.department_cockpit import _user_images, _user_label, role_shortlist_users
from phamos.phamos.page.sales_action_panel.sales_action_panel import LEAD_STATUSES

LEAD_ROLES = ("System Manager", "Sales Manager", "Sales User")

LEAD_LIST_LIMIT = 1000

LEAD_LIST_FIELDS = [
	"name",
	"lead_name",
	"company_name",
	"status",
	"lead_owner",
	"phone",
	"mobile_no",
	"email_id",
	"territory",
	"custom_next_followup",
	"custom_status_comment",
	"creation",
	"modified",
]

# Fields editable inline from the Follow Ups cockpit — transactional fields
# a rep changes on every follow-up, plus master-data fields that start out
# unset and get filled in over time. `qualified_by`/`qualified_on` stay
# system-set (not in this list) since they're set by Frappe's own qualify
# flow, not typed in directly.
LEAD_TRANSACTIONAL_FIELDS = (
	"status",
	"custom_next_followup",
	"qualification_status",
	"custom_status_comment",
	"lead_owner",
	"custom_planned_start",
)
LEAD_MASTER_FIELDS = (
	"company_name",
	"website",
	"city",
	"state",
	"country",
	"territory",
	"source",
	"industry",
	"no_of_employees",
	"market_segment",
	"annual_revenue",
	"request_type",
)
LEAD_EDITABLE_FIELDS = LEAD_TRANSACTIONAL_FIELDS + LEAD_MASTER_FIELDS

LOST_STATUSES = ("Do Not Contact", "Lost Quotation")
CONVERTED_STATUS = "Converted"

WEBSITE_CHECK_TIMEOUT = 5
# Plain browser UA: some sites serve different headers (or refuse outright) to
# unknown clients, which would make an embeddable site look un-embeddable.
WEBSITE_CHECK_USER_AGENT = (
	"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
	"(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)


def normalize_website(url):
	"""Add https:// when the stored value omits a scheme."""
	url = (url or "").strip()
	if not url:
		return ""
	if not re.match(r"^https?://", url, re.IGNORECASE):
		url = f"https://{url}"
	return url


def _is_public_http_url(url):
	"""Reject non-HTTP schemes and anything resolving to a non-public address.

	The URL here comes from user input and is fetched server-side, so this
	guards against pointing the check at loopback/private infrastructure.
	"""
	parsed = urlparse(url)
	if parsed.scheme not in ("http", "https"):
		return False
	if not parsed.hostname:
		return False

	try:
		addresses = socket.getaddrinfo(parsed.hostname, None)
	except (socket.gaierror, UnicodeError):
		return False

	for address in addresses:
		try:
			ip = ipaddress.ip_address(address[4][0])
		except ValueError:
			return False
		if (
			ip.is_private
			or ip.is_loopback
			or ip.is_link_local
			or ip.is_reserved
			or ip.is_multicast
			or ip.is_unspecified
		):
			return False

	return True


def _frame_ancestors_allow_embedding(csp_header):
	"""True unless a frame-ancestors directive rules this site out.

	Only a wildcard (or a bare `https:`) source is treated as embeddable —
	'none'/'self'/an explicit host list all mean our cockpit can't frame it.
	"""
	if not csp_header:
		return True

	for directive in csp_header.split(";"):
		parts = directive.strip().split()
		if not parts or parts[0].lower() != "frame-ancestors":
			continue
		sources = [p.strip().lower() for p in parts[1:]]
		return any(source in ("*", "https:", "http:") for source in sources)

	return True


@frappe.whitelist()
def check_website_embeddable(url):
	"""Report whether a website can be shown in an iframe.

	X-Frame-Options / CSP frame-ancestors can only be read from the response
	headers, and a browser gives no usable signal when it blocks a frame — so
	the cockpit asks here first and opens a new tab instead when the answer is
	no, rather than showing the user an empty dialog.
	"""
	_check_lead_access()

	normalized = normalize_website(url)
	if not normalized or not _is_public_http_url(normalized):
		return {"url": normalized, "embeddable": False, "reason": "unreachable"}

	headers = {"User-Agent": WEBSITE_CHECK_USER_AGENT}
	try:
		response = requests.head(
			normalized, timeout=WEBSITE_CHECK_TIMEOUT, allow_redirects=True, headers=headers
		)
		if response.status_code >= 400:
			# Plenty of sites don't answer HEAD properly; fall back to GET.
			response = requests.get(
				normalized, timeout=WEBSITE_CHECK_TIMEOUT, allow_redirects=True, headers=headers, stream=True
			)
			response.close()
	except requests.RequestException:
		return {"url": normalized, "embeddable": False, "reason": "unreachable"}

	final_url = response.url or normalized
	# Re-check after redirects: the first hop being public doesn't mean the last one is.
	if not _is_public_http_url(final_url):
		return {"url": normalized, "embeddable": False, "reason": "unreachable"}

	if response.status_code >= 400:
		return {"url": final_url, "embeddable": False, "reason": "unreachable"}

	x_frame_options = (response.headers.get("X-Frame-Options") or "").strip().lower()
	if x_frame_options:
		return {"url": final_url, "embeddable": False, "reason": "blocked"}

	if not _frame_ancestors_allow_embedding(response.headers.get("Content-Security-Policy")):
		return {"url": final_url, "embeddable": False, "reason": "blocked"}

	return {"url": final_url, "embeddable": True, "reason": ""}


def _check_lead_access():
	"""Raise unless the user can read Lead and holds a Sales role."""
	frappe.has_permission("Lead", "read", throw=True)
	if frappe.session.user == "Administrator":
		return
	if not set(frappe.get_roles()) & set(LEAD_ROLES):
		frappe.throw(_("You need a Sales role to use the Leads cockpit."), frappe.PermissionError)


def _lead_bucket(status):
	if status == CONVERTED_STATUS:
		return "converted"
	if status in LOST_STATUSES:
		return "lost"
	return "open"


def _is_overdue(next_followup, today_date=None):
	"""Overdue only once the due date has passed — a lead due today is not."""
	if not next_followup:
		return False
	return getdate(next_followup) < (today_date or getdate())


def _serialize_lead_row(row, owner_names, owner_images, today_date, next_steps=None):
	owner = row.get("lead_owner")
	row["owner_name"] = owner_names.get(owner) or owner
	row["owner_image"] = owner_images.get(owner) or ""
	row["overdue"] = _is_overdue(row.get("custom_next_followup"), today_date)

	step = (next_steps or {}).get(row.get("name"))
	row["next_step"] = step.get("next_step") if step else None
	row["next_step_date"] = step.get("date") if step else None
	row["next_step_overdue"] = _is_overdue(step.get("date"), today_date) if step else False
	return row


def _soonest_next_steps(lead_names):
	"""The single most pressing next step per Lead, for the list view.

	One query for the whole page rather than one per row — the list is the
	place where an N+1 would actually be felt.
	"""
	if not lead_names:
		return {}

	rows = frappe.get_all(
		"Lead Next Step",
		filters={"parent": ["in", lead_names], "parenttype": "Lead"},
		fields=["parent", "next_step", "date"],
		# Undated steps last, so a dated one always wins as "what's next".
		order_by="date is null asc, date asc, idx asc",
	)

	soonest = {}
	for row in rows:
		if not (row.next_step or "").strip():
			continue
		soonest.setdefault(row.parent, {"next_step": row.next_step, "date": row.date})
	return soonest


@frappe.whitelist()
def get_leads():
	"""Return all non-disabled Leads, sorted for follow-up triage.

	Leads with no `custom_next_followup` sort first (need triage), then leads
	with a date, ascending (soonest/most overdue first) — MariaDB sorts NULL
	first under `IS NULL ... DESC`.
	"""
	_check_lead_access()

	rows = frappe.get_all(
		"Lead",
		filters={"disabled": 0},
		fields=LEAD_LIST_FIELDS,
		order_by="custom_next_followup is null desc, custom_next_followup asc",
		limit_page_length=LEAD_LIST_LIMIT + 1,
	)
	truncated = len(rows) > LEAD_LIST_LIMIT
	rows = rows[:LEAD_LIST_LIMIT]

	owners = list(dict.fromkeys(r.lead_owner for r in rows if r.lead_owner))
	owner_names = {owner: _user_label(owner) for owner in owners}
	owner_images = dict(zip(owners, _user_images(owners)))

	today_date = getdate()
	next_steps = _soonest_next_steps([r.name for r in rows])
	items = [
		_serialize_lead_row(row, owner_names, owner_images, today_date, next_steps) for row in rows
	]

	return {"items": items, "truncated": truncated, "statuses": LEAD_STATUSES}


def _serialize_notes(doc):
	"""Serialize the Lead's native `notes` child table (CRM Note), newest first."""
	authors = list(dict.fromkeys(n.added_by for n in doc.notes if n.added_by))
	author_names = {author: _user_label(author) for author in authors}
	notes = [
		{
			"name": n.name,
			"note": n.note,
			"added_by": n.added_by,
			"added_by_name": author_names.get(n.added_by) or n.added_by,
			"added_on": n.added_on,
		}
		for n in doc.notes
	]
	notes.sort(key=lambda n: n["added_on"] or "", reverse=True)
	return notes


def _serialize_modules(doc):
	"""Implementation modules linked to this lead."""
	return [
		{"name": row.name, "module": row.module, "module_name": row.module_name or row.module}
		for row in (doc.get("custom_modules") or [])
	]


@frappe.whitelist()
def get_module_suggestions(limit=12):
	"""Modules offered as one-click adds, standard ones first."""
	_check_lead_access()
	rows = frappe.get_all(
		"Implementation Module",
		fields=["name", "module_name", "is_standard", "is_required"],
		order_by="is_required desc, is_standard desc, module_name asc",
		limit_page_length=limit,
	)
	return [
		{"name": row.name, "module_name": row.module_name or row.name}
		for row in rows
	]


@frappe.whitelist(methods=["POST"])
def set_lead_modules(lead, modules=None):
	"""Replace the Lead's linked modules.

	Wholesale replace like the other cockpit tables; duplicates are dropped
	so adding the same module twice is a no-op rather than an error.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	if isinstance(modules, str):
		modules = json.loads(modules)

	doc.set("custom_modules", [])
	seen = set()
	for module in modules or []:
		name = module.get("module") if isinstance(module, dict) else module
		if not name or name in seen:
			continue
		seen.add(name)
		doc.append("custom_modules", {"module": name})

	doc.save()
	return _serialize_modules(doc)


PLANNED_START_STEP = "Planned start"


def _sync_planned_start_next_step(doc, planned_start):
	"""Keep a single "Planned start" next step in step with the date.

	Matched on its label so moving the planned start updates that row
	rather than piling up a new one each time.
	"""
	if not planned_start:
		return

	for row in doc.get("custom_next_steps") or []:
		if (row.next_step or "").strip().lower() == PLANNED_START_STEP.lower():
			row.date = planned_start
			return

	doc.append("custom_next_steps", {"next_step": PLANNED_START_STEP, "date": planned_start})


def _next_step_sort_key(row):
	"""Date ascending, undated rows last."""
	date = row.get("date")
	return (not date, str(date or ""))


def _serialize_next_steps(doc):
	"""Rows of the Lead's `custom_next_steps` child table, by date."""
	rows = [
		{"name": row.name, "next_step": row.next_step, "date": row.date}
		for row in (doc.get("custom_next_steps") or [])
	]
	return sorted(rows, key=_next_step_sort_key)


def _serialize_hours_predictions(doc):
	"""Predicted hours per month, earliest month first."""
	rows = [
		{"name": row.name, "month_start": row.month_start, "hours": row.hours}
		for row in (doc.get("custom_hours_predictions") or [])
	]
	return sorted(rows, key=lambda r: str(r["month_start"] or ""))


def _serialize_lead_detail(doc):
	"""Identity, master-data, and transactional fields — no notes/communications.

	Notes and Communications are heavier (child table + separate doctype
	query) and only needed by the Communication/Notes/Activities feed, so
	they're served separately by `get_lead_activity` (and `notes` alone via
	this same function is unnecessary — the feed calls `get_lead_activity`
	and `_serialize_notes` is still used there for the Notes tab).
	"""
	return {
		"name": doc.name,
		# Master data — company/contact identity and firmographics; rarely
		# changes once set, no inline editing in the cockpit for v1.
		"lead_name": doc.lead_name,
		"company_name": doc.company_name,
		"email_id": doc.email_id,
		"phone": doc.phone,
		"mobile_no": doc.mobile_no,
		"website": doc.website,
		"city": doc.city,
		"state": doc.state,
		"country": doc.country,
		"territory": doc.territory,
		"source": doc.source,
		"industry": doc.industry,
		"no_of_employees": doc.no_of_employees,
		"market_segment": doc.market_segment,
		"annual_revenue": doc.annual_revenue,
		"request_type": doc.request_type,
		# Transactional data — changes on every follow-up, inline-editable
		# via update_lead.
		"status": doc.status,
		"lead_owner": doc.lead_owner,
		"lead_owner_name": _user_label(doc.lead_owner) if doc.lead_owner else None,
		"lead_owner_image": frappe.db.get_value("User", doc.lead_owner, "user_image") if doc.lead_owner else "",
		"custom_next_followup": doc.custom_next_followup,
		"custom_planned_start": doc.custom_planned_start,
		"hours_predictions": _serialize_hours_predictions(doc),
		"custom_status_comment": doc.custom_status_comment,
		# Who last changed the comment and when — Desk shows this alongside the
		# comment, so the cockpit shouldn't be the surface that drops it.
		"custom_status_comment_modified_by": doc.custom_status_comment_modified_by,
		"custom_status_comment_modified_by_name": _user_label(doc.custom_status_comment_modified_by)
		if doc.custom_status_comment_modified_by
		else None,
		"custom_status_comment_modified_date": doc.custom_status_comment_modified_date,
		"qualification_status": doc.qualification_status,
		"qualified_by": doc.qualified_by,
		"qualified_by_name": _user_label(doc.qualified_by) if doc.qualified_by else None,
		"qualified_on": doc.qualified_on,
		"creation": doc.creation,
		"modified": doc.modified,
		"next_steps": _serialize_next_steps(doc),
		"modules": _serialize_modules(doc),
		"desk_url": f"/app/lead/{doc.name}",
	}


@frappe.whitelist()
def get_lead_owners():
	"""Enabled users holding a Sales role — candidates for Lead Owner."""
	_check_lead_access()
	return role_shortlist_users(LEAD_ROLES)


@frappe.whitelist()
def get_lead(name):
	"""Return Lead master + transactional data for the Sales cockpit detail view."""
	frappe.has_permission("Lead", "read", throw=True)
	doc = frappe.get_doc("Lead", name)
	doc.check_permission("read")
	return _serialize_lead_detail(doc)


@frappe.whitelist(methods=["POST"])
def update_lead(
	name,
	status=None,
	custom_next_followup=None,
	qualification_status=None,
	custom_status_comment=None,
	lead_owner=None,
	custom_planned_start=None,
	company_name=None,
	website=None,
	city=None,
	state=None,
	country=None,
	territory=None,
	source=None,
	industry=None,
	no_of_employees=None,
	market_segment=None,
	annual_revenue=None,
	request_type=None,
	if_modified=None,
):
	"""Update whitelisted transactional + master-data Lead fields, autosave-style.

	`if_modified` is the `modified` timestamp the client last saw. A
	mismatch means someone else saved this Lead since the client loaded
	it. This is a low-friction autosave, not a locking form, so the edit
	is still saved — the mismatch is only reported back as `conflict` so
	the caller can warn the user their change may have overwritten
	someone else's, rather than losing it silently (same pattern as
	department_cockpit.update_issue).

	Lead's own mandatory-comment-on-"Do Not Contact" validation still
	fires from `doc.save()`; a status change to "Do Not Contact" without
	`custom_status_comment` in the same call will raise, and the caller
	should let the Status Comment field pick that up on the next save.
	`territory`/`source`/`industry`/`market_segment` are Link fields —
	`doc.save()` will raise if a typed value doesn't match an existing
	record, surfaced to the caller like any other save error.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", name)
	doc.check_permission("write")
	conflict = bool(if_modified) and str(doc.modified) != str(if_modified)

	fields = {
		"status": status,
		"custom_next_followup": custom_next_followup,
		"qualification_status": qualification_status,
		"custom_status_comment": custom_status_comment,
		"lead_owner": lead_owner,
		"custom_planned_start": custom_planned_start,
		"company_name": company_name,
		"website": website,
		"city": city,
		"state": state,
		"country": country,
		"territory": territory,
		"source": source,
		"industry": industry,
		"no_of_employees": no_of_employees,
		"market_segment": market_segment,
		"annual_revenue": annual_revenue,
		"request_type": request_type,
	}
	updates = {k: v for k, v in fields.items() if v is not None}
	unknown = set(updates) - set(LEAD_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("Invalid Lead field(s): {0}").format(", ".join(sorted(unknown))))
	if not updates:
		frappe.throw(_("No fields to update"))

	if "website" in updates:
		updates["website"] = normalize_website(updates["website"])

	# Keep the status-comment stamps in step with the Desk client script
	# (public/js/lead.js), which sets them whenever the comment changes —
	# otherwise editing the comment from the cockpit leaves them pointing at
	# whoever last touched it in Desk. Only on an actual change, so routine
	# autosaves don't rewrite them.
	if "custom_status_comment" in updates and updates["custom_status_comment"] != (
		doc.custom_status_comment or ""
	):
		updates["custom_status_comment_modified_by"] = frappe.session.user
		updates["custom_status_comment_modified_date"] = now_datetime()

	for key, value in updates.items():
		doc.set(key, value)

	if updates.get("custom_planned_start"):
		_sync_planned_start_next_step(doc, updates["custom_planned_start"])

	doc.save()
	result = get_lead(name)
	result["conflict"] = conflict
	return result


@frappe.whitelist(methods=["POST"])
def set_lead_next_steps(lead, rows=None):
	"""Replace the Lead's Next Steps table with `rows`.

	The cockpit edits the table as a whole (add/edit/delete then save), so
	replacing it wholesale avoids matching up child-row identities; blank
	rows are dropped rather than failing the required `next_step` field.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	if isinstance(rows, str):
		rows = json.loads(rows)

	kept = [row for row in (rows or []) if (row.get("next_step") or "").strip()]

	doc.set("custom_next_steps", [])
	# Stored in date order so the table reads chronologically everywhere,
	# including the Desk grid — not just in the cockpit.
	for row in sorted(kept, key=_next_step_sort_key):
		doc.append(
			"custom_next_steps",
			{"next_step": row["next_step"].strip(), "date": row.get("date") or None},
		)

	doc.save()
	return _serialize_next_steps(doc)


def _field_label(meta, fieldname):
	field = meta.get_field(fieldname)
	return field.label if field and field.label else fieldname


def _child_row_summary(meta, table_fieldname, row):
	"""Readable one-liner for a child row, built from its list-view fields."""
	table_field = meta.get_field(table_fieldname)
	if not (table_field and table_field.options):
		return ""

	child_meta = frappe.get_meta(table_field.options)
	values = [
		str(row.get(df.fieldname))
		for df in child_meta.fields
		if df.in_list_view and row.get(df.fieldname)
	]
	return " · ".join(values)


@frappe.whitelist(methods=["POST"])
def set_lead_hours_predictions(lead, rows=None):
	"""Replace the Lead's hours-per-month predictions.

	Replaced wholesale for the same reason as Next Steps: the cockpit edits
	the whole table at once, and months with no number yet are simply
	dropped rather than stored as zeros.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	if isinstance(rows, str):
		rows = json.loads(rows)

	doc.set("custom_hours_predictions", [])
	for row in sorted(rows or [], key=lambda r: str(r.get("month_start") or "")):
		month_start = row.get("month_start")
		hours = row.get("hours")
		if not month_start or hours in (None, ""):
			continue
		# Whole hours, rounded here so the stored value and the value echoed
		# back always agree — MySQL would otherwise silently truncate an Int
		# column and the caller would render something the DB doesn't hold.
		doc.append(
			"custom_hours_predictions",
			{"month_start": month_start, "hours": int(round(float(hours)))},
		)

	doc.save()
	return _serialize_hours_predictions(doc)


def _lead_communications(lead, fields, limit=20):
	"""Every email on this Lead's timeline, however it got attached.

	A Communication reaches a document two ways: `reference_doctype`/
	`reference_name` on the Communication itself, or a row in its
	`Communication Link` child table. Inbound mail matched to a lead by
	address typically arrives by the second route, so querying only the
	reference fields silently misses most of a real conversation — which is
	why Frappe's own timeline unions both.
	"""
	rows = frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Lead", "reference_name": lead},
		fields=fields,
		order_by="communication_date desc",
		limit_page_length=limit,
	)
	found = {row["name"]: row for row in rows}

	linked = frappe.get_all(
		"Communication Link",
		filters={"link_doctype": "Lead", "link_name": lead},
		pluck="parent",
	)
	unseen = [name for name in linked if name not in found]
	if unseen:
		for row in frappe.get_all(
			"Communication",
			filters={"name": ("in", unseen)},
			fields=fields,
			order_by="communication_date desc",
			limit_page_length=limit,
		):
			found[row["name"]] = row

	merged = sorted(
		found.values(), key=lambda r: str(r.get("communication_date") or ""), reverse=True
	)
	return merged[:limit]


def _thread_key(subject):
	"""Normalised subject used to group a conversation together.

	Reply/forward prefixes accumulate ("Re: Fwd: Re: ..."), and localised
	ones are common in German mail clients, so strip them repeatedly until
	the underlying subject is left.
	"""
	clean = (subject or "").strip()
	while True:
		stripped = re.sub(r"^\s*(re|fwd|fw|aw|wg)\s*:\s*", "", clean, flags=re.IGNORECASE)
		if stripped == clean:
			break
		clean = stripped
	return clean.casefold()


def _contact_suggestions(lead, lead_doc):
	"""Addresses worth offering: the lead itself, its Contacts, and anyone
	already in the conversation."""
	found = {}

	def add(email, label, source):
		email = (email or "").strip()
		if not email or email.lower() in found:
			return
		found[email.lower()] = {"email": email, "label": label or email, "source": source}

	add(lead_doc.email_id, lead_doc.lead_name or lead, "Lead")

	contact_names = frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Lead", "link_name": lead, "parenttype": "Contact"},
		pluck="parent",
	)
	if contact_names:
		for contact in frappe.get_all(
			"Contact",
			filters={"name": ("in", contact_names)},
			fields=["name", "first_name", "last_name", "email_id"],
		):
			label = " ".join(filter(None, [contact.first_name, contact.last_name])) or contact.name
			add(contact.email_id, label, "Contact")
			for row in frappe.get_all(
				"Contact Email", filters={"parent": contact.name}, fields=["email_id"]
			):
				add(row.email_id, label, "Contact")

	# Anyone already on the thread — the practical source of addresses that
	# were never captured as Contacts.
	for comm in _lead_communications(
		lead, fields=["name", "communication_date", "sender", "recipients", "cc"], limit=50
	):
		for field in ("sender", "recipients", "cc"):
			for address in (comm.get(field) or "").split(","):
				address = address.strip()
				if address:
					add(address, address, "Conversation")

	return list(found.values())


@frappe.whitelist()
def get_lead_email_context(lead):
	"""Suggested recipients and available templates for the compose dialog."""
	_check_lead_access()
	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	templates = frappe.get_all(
		"Email Template",
		fields=["name", "subject"],
		order_by="name asc",
		limit_page_length=100,
	)

	signature, footer = _email_signature_and_footer()

	return {
		"suggestions": _contact_suggestions(lead, lead_doc),
		"templates": templates,
		"signature": signature,
		"footer": footer,
	}


def _email_signature_and_footer():
	"""What gets appended to an outgoing mail, so the dialog can show it.

	Two different things, and they behave differently: the signature is part
	of the body and the user can edit it, while the footer is assembled by
	Frappe at send time (Email Account footer, System Settings' address and
	the standard footer) and can only be previewed.
	"""
	from frappe.email.doctype.email_account.email_account import EmailAccount
	from frappe.email.email_body import get_footer

	email_account = None
	try:
		# The same order Frappe resolves an outgoing account in: an account that
		# appends to Lead, else the default outgoing one. `find_outgoing` wraps
		# its result in a dict, so go through the two lookups it uses.
		email_account = EmailAccount.find_one_by_filters(
			enable_outgoing=1, enable_incoming=1, append_to="Lead"
		) or EmailAccount.find_default_outgoing()
	except Exception:
		# No outgoing account configured is a normal state on a fresh site;
		# it only means there's no account-level footer to show.
		pass

	signature = frappe.db.get_value("User", frappe.session.user, "email_signature")
	if not signature and email_account and email_account.get("add_signature"):
		signature = email_account.get("signature")

	signature = (signature or "").strip()
	if signature and "<" not in signature:
		signature = signature.replace("\n", "<br>")

	try:
		footer = get_footer(email_account) or ""
	except Exception:
		footer = ""

	return signature, footer.strip()


@frappe.whitelist()
def render_lead_email_template(lead, template):
	"""Render an Email Template against this Lead."""
	_check_lead_access()
	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	from frappe.email.doctype.email_template.email_template import get_email_template

	return get_email_template(template, lead_doc.as_dict())


@frappe.whitelist()
def search_email_recipients(lead, txt="", limit=10):
	"""Addresses matching `txt` for the compose dialog's recipient fields.

	Searches what's already connected to the lead first (its own address,
	its Contacts, anyone on the thread), then falls back to Contacts at
	large so an address that isn't linked yet can still be picked.
	"""
	_check_lead_access()
	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	txt = (txt or "").strip().casefold()
	limit = frappe.utils.cint(limit) or 10

	found = {}
	for suggestion in _contact_suggestions(lead, lead_doc):
		haystack = f"{suggestion['label']} {suggestion['email']}".casefold()
		if not txt or txt in haystack:
			found[suggestion["email"].casefold()] = suggestion

	if txt and len(found) < limit:
		like = f"%{txt}%"
		contacts = frappe.get_all(
			"Contact",
			or_filters=[
				["first_name", "like", like],
				["last_name", "like", like],
				["email_id", "like", like],
			],
			fields=["name", "first_name", "last_name", "email_id"],
			limit_page_length=limit,
		)
		for contact in contacts:
			if not contact.email_id or contact.email_id.casefold() in found:
				continue
			label = " ".join(filter(None, [contact.first_name, contact.last_name])) or contact.name
			found[contact.email_id.casefold()] = {
				"email": contact.email_id,
				"label": label,
				"source": "Contact",
			}

	return list(found.values())[:limit]


@frappe.whitelist()
def get_contact_emails(contact):
	"""Addresses on a Contact, for the 'choose an existing contact' picker."""
	_check_lead_access()
	doc = frappe.get_doc("Contact", contact)
	doc.check_permission("read")

	label = " ".join(filter(None, [doc.first_name, doc.last_name])) or doc.name
	emails = [row.email_id for row in (doc.email_ids or []) if row.email_id]
	if doc.email_id and doc.email_id not in emails:
		emails.insert(0, doc.email_id)
	return {"label": label, "emails": emails}


def _linked_contact_names(lead):
	"""Contacts pointing at this Lead, via the Dynamic Link they're joined by."""
	return frappe.get_all(
		"Dynamic Link",
		filters={"link_doctype": "Lead", "link_name": lead, "parenttype": "Contact"},
		pluck="parent",
	)


def _contact_addresses(doc):
	"""Every address and number on a Contact, primary one first."""
	emails = [row.email_id for row in (doc.email_ids or []) if row.email_id]
	if doc.email_id and doc.email_id not in emails:
		emails.insert(0, doc.email_id)

	phones = [row.phone for row in (doc.phone_nos or []) if row.phone]
	for value in (doc.mobile_no, doc.phone):
		if value and value not in phones:
			phones.insert(0, value)

	return emails, phones


def _serialize_contact(doc, lead_doc):
	emails, phones = _contact_addresses(doc)
	lead_email = (lead_doc.email_id or "").strip().casefold()
	lead_numbers = {_digits(n) for n in (lead_doc.mobile_no, lead_doc.phone) if _digits(n)}
	full_name = doc.full_name or " ".join(filter(None, [doc.first_name, doc.last_name])) or doc.name

	# "Primary" isn't stored on the Lead — the Lead simply carries a copy of one
	# person's details. So a Contact is the primary one when those details are
	# its own.
	is_primary = bool(
		(lead_email and lead_email in {e.strip().casefold() for e in emails})
		or (not lead_email and lead_numbers and lead_numbers & {_digits(p) for p in phones})
		or (not lead_email and not lead_numbers and full_name == (lead_doc.lead_name or ""))
	)

	return {
		"name": doc.name,
		"full_name": full_name,
		"salutation": doc.salutation,
		"designation": doc.designation,
		"department": doc.department,
		"company_name": doc.company_name,
		"status": doc.status,
		"image": doc.image,
		"email_id": emails[0] if emails else "",
		"emails": emails,
		"phones": phones,
		"mobile_no": doc.mobile_no,
		"phone": doc.phone,
		"is_primary": is_primary,
		# When the contact was put on file — the timeline places it there.
		"creation": doc.creation,
	}


def _digits(value):
	return re.sub(r"\D", "", value or "")


@frappe.whitelist()
def get_lead_contacts(lead):
	"""Contacts linked to this Lead, and whether the Lead's own details are one of them."""
	_check_lead_access()
	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	contacts = []
	for name in _linked_contact_names(lead):
		doc = frappe.get_doc("Contact", name)
		if doc.has_permission("read"):
			contacts.append(_serialize_contact(doc, lead_doc))

	# Primary first, and among them the one that actually carries details —
	# a lead often has an auto-created contact holding nothing but a name
	# alongside the real one, and the header calls the first primary it finds.
	contacts.sort(
		key=lambda c: (
			not c["is_primary"],
			not (c["phones"] or c["emails"]),
			c["full_name"].casefold(),
		)
	)

	return {
		"contacts": contacts,
		"primary": {
			"lead_name": lead_doc.lead_name,
			"email_id": lead_doc.email_id,
			"phone": lead_doc.phone,
			"mobile_no": lead_doc.mobile_no,
		},
		# False means the details in the header belong to nobody on file.
		"primary_tracked": any(c["is_primary"] for c in contacts),
	}


@frappe.whitelist(methods=["POST"])
def set_lead_primary_contact(lead, contact, untracked_action=None):
	"""Promote a linked Contact to the details the Lead carries.

	The Lead stores a copy of one person's name, email and numbers rather than
	pointing at a Contact, so promoting someone overwrites that copy. When the
	details being overwritten aren't held by any Contact, they'd be lost — so
	the caller is asked what to do first, rather than silently discarding them.
	"""
	_check_lead_access()
	frappe.has_permission("Lead", "write", throw=True)

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("write")

	if contact not in _linked_contact_names(lead):
		frappe.throw(_("That contact is not linked to this lead."))

	contact_doc = frappe.get_doc("Contact", contact)
	contact_doc.check_permission("read")

	current = {
		"lead_name": lead_doc.lead_name,
		"email_id": lead_doc.email_id,
		"phone": lead_doc.phone,
		"mobile_no": lead_doc.mobile_no,
	}
	has_details = any(current.values())
	tracked = get_lead_contacts(lead)["primary_tracked"]

	if has_details and not tracked and untracked_action not in ("create", "discard"):
		return {"needs_decision": True, "current": current}

	if has_details and not tracked and untracked_action == "create":
		created = lead_doc.create_contact()
		created.append(
			"links", {"link_doctype": "Lead", "link_name": lead_doc.name, "link_title": lead_doc.lead_name}
		)
		created.save(ignore_permissions=True)

	emails, phones = _contact_addresses(contact_doc)
	lead_doc.salutation = contact_doc.salutation
	lead_doc.first_name = contact_doc.first_name
	lead_doc.middle_name = contact_doc.middle_name
	lead_doc.last_name = contact_doc.last_name
	# Recomputed from the name parts in Lead.set_full_name on validate; set it
	# too so a contact with no first name still leaves the Lead named.
	lead_doc.lead_name = (
		contact_doc.full_name
		or " ".join(filter(None, [contact_doc.first_name, contact_doc.last_name]))
		or lead_doc.lead_name
	)
	if contact_doc.gender:
		lead_doc.gender = contact_doc.gender
	lead_doc.email_id = emails[0] if emails else None
	lead_doc.mobile_no = contact_doc.mobile_no or (phones[0] if phones else None)
	lead_doc.phone = contact_doc.phone or None
	lead_doc.save()

	return {"ok": True, "lead": _serialize_lead_detail(frappe.get_doc("Lead", lead))}


@frappe.whitelist(methods=["POST"])
def send_lead_email(
	lead, recipients, subject, content, cc=None, bcc=None, in_reply_to=None, attachments=None, send=1
):
	"""Send an email from the system, linked to the Lead.

	Goes through Frappe's own `communication.email.make`, so the outgoing
	message is recorded as a Communication against this Lead and replies
	thread back to it — which a mailto: handoff can't do, since the mail
	never passes through the system at all.
	"""
	_check_lead_access()
	frappe.has_permission("Lead", "write", throw=True)

	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("read")

	recipients = (recipients or "").strip()
	subject = (subject or "").strip()
	if not recipients:
		frappe.throw(_("At least one recipient is required."))
	if not subject:
		frappe.throw(_("A subject is required."))

	# Files the dialog uploaded against this Lead; `make` copies each one onto
	# the Communication, so only names the user actually attached are passed on.
	attachments = _clean_attachments(lead, attachments)

	from frappe.core.doctype.communication.email import make

	result = make(
		doctype="Lead",
		name=lead,
		content=content or "",
		subject=subject,
		recipients=recipients,
		cc=cc or None,
		bcc=bcc or None,
		in_reply_to=in_reply_to or None,
		attachments=attachments or None,
		communication_medium="Email",
		sent_or_received="Sent",
		send_email=frappe.utils.cint(send),
	)
	return {"name": result.get("name")}


def _clean_attachments(lead, attachments):
	"""File names that really belong to this Lead, so a crafted payload can't
	pull an unrelated private file into an outgoing email."""
	if isinstance(attachments, str):
		attachments = frappe.parse_json(attachments)
	if not attachments:
		return []

	names = [str(a) for a in attachments if a]
	if not names:
		return []

	return frappe.get_all(
		"File",
		filters={
			"name": ["in", names],
			"attached_to_doctype": "Lead",
			"attached_to_name": lead,
		},
		pluck="name",
	)


@frappe.whitelist(methods=["POST"])
def remove_lead_attachment(lead, file):
	"""Drop a file the user attached in the compose dialog and then changed
	their mind about, so abandoned uploads don't pile up on the Lead."""
	_check_lead_access()
	frappe.has_permission("Lead", "write", throw=True)

	if not _clean_attachments(lead, [file]):
		frappe.throw(_("That file is not attached to this lead."))

	frappe.delete_doc("File", file)
	return {"ok": True}


@frappe.whitelist(methods=["POST"])
def update_lead_note(lead, note_name, content):
	"""Edit an existing note on a Lead.

	Uses ERPNext's own `CRMNote.edit_note` (the mechanism behind the Desk
	form's note editing) rather than writing the child row directly, so
	both paths behave the same.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	content = (content or "").strip()
	if not content:
		frappe.throw(_("A note can't be empty."))

	if not any(str(row.name) == str(note_name) for row in (doc.notes or [])):
		frappe.throw(_("That note is no longer on this lead."))

	doc.edit_note(content, str(note_name))
	return _serialize_notes(frappe.get_doc("Lead", lead))


def _format_lead_activities(docinfo):
	"""Field-change (Version) and system comment entries, newest first.

	Sentence construction ("changed from X to Y") is left to the frontend —
	this just resolves each changed fieldname to its Lead form label. Child
	table rows (e.g. Next Steps) come through Version's added/removed/
	row_changed buckets rather than `changed`.
	"""
	meta = frappe.get_meta("Lead")
	activities = []

	for version in docinfo.get("versions") or []:
		try:
			data = json.loads(version.get("data") or "{}")
		except (TypeError, ValueError):
			continue

		owner = version.get("owner")
		creation = version.get("creation")

		for fieldname, old, new in data.get("changed") or []:
			activities.append(
				{
					"kind": "field_change",
					"field": fieldname,
					"label": _field_label(meta, fieldname),
					"old": old,
					"new": new,
					"owner": owner,
					"creation": creation,
				}
			)

		for kind, bucket in (("row_added", "added"), ("row_removed", "removed")):
			for fieldname, row in data.get(bucket) or []:
				activities.append(
					{
						"kind": kind,
						"field": fieldname,
						"label": _field_label(meta, fieldname),
						"summary": _child_row_summary(meta, fieldname, row),
						"owner": owner,
						"creation": creation,
					}
				)

		for entry in data.get("row_changed") or []:
			# [table_fieldname, row_index, row_name, [[fieldname, old, new], ...]]
			fieldname, changes = entry[0], entry[3]
			table_label = _field_label(meta, fieldname)
			table_field = meta.get_field(fieldname)
			child_meta = frappe.get_meta(table_field.options) if table_field and table_field.options else None
			for child_fieldname, old, new in changes:
				child_field = child_meta.get_field(child_fieldname) if child_meta else None
				child_label = child_field.label if child_field and child_field.label else child_fieldname
				activities.append(
					{
						"kind": "field_change",
						"field": f"{fieldname}.{child_fieldname}",
						"label": f"{table_label} · {child_label}",
						"old": old,
						"new": new,
						"owner": owner,
						"creation": creation,
					}
				)

	for bucket in ("info_logs", "workflow_logs", "assignment_logs"):
		for comment in docinfo.get(bucket) or []:
			activities.append(
				{
					"kind": "comment",
					"content": comment.get("content"),
					"owner": comment.get("owner"),
					"creation": comment.get("creation"),
				}
			)

	activities.sort(key=lambda a: a.get("creation") or "", reverse=True)
	return activities


@frappe.whitelist()
def get_lead_activity(name):
	"""Return Communications and change/comment Activities for a Lead.

	Notes stay out of this (they're Lead's own native `notes` child table,
	served via `_serialize_notes` below). Activities are built from
	Frappe's own `get_docinfo` — the same aggregation the Desk form's
	timeline uses — for Versions and system comments, rather than
	re-deriving Version-diff parsing by hand; Communications keep the
	existing direct query since `get_docinfo`'s own field selection for
	them isn't guaranteed to include everything the feed wants (e.g.
	`sent_or_received`).
	"""
	frappe.has_permission("Lead", "read", throw=True)
	doc = frappe.get_doc("Lead", name)
	doc.check_permission("read")

	from frappe.desk.form.load import get_docinfo

	get_docinfo(doc=doc)
	docinfo = frappe.response.pop("docinfo", None) or {}

	communications = _lead_communications(
		doc.name,
		fields=[
			"name",
			"subject",
			"content",
			"sent_or_received",
			"communication_date",
			"sender",
			"recipients",
			"cc",
			"in_reply_to",
		],
		limit=20,
	)

	# Tag each message with its conversation so the UI can show them as one.
	thread_counts = {}
	for row in communications:
		row["thread_key"] = _thread_key(row.subject)
		thread_counts[row["thread_key"]] = thread_counts.get(row["thread_key"], 0) + 1
	for row in communications:
		row["thread_size"] = thread_counts[row["thread_key"]]
		# The message as it was actually written, not a flattened transcript of
		# it. Inbound mail is untrusted HTML, so it goes through Frappe's own
		# email cleaner (script/style stripped, CSS limited to an allowlist)
		# before the cockpit renders it.
		row["content_html"] = clean_email_html(row.get("content") or "")

	return {
		"notes": _serialize_notes(doc),
		"communications": communications,
		"activities": _format_lead_activities(docinfo),
		"opportunities": _lead_opportunities(doc.name),
		"quotations": _lead_quotations(doc.name),
	}


def _lead_opportunities(lead):
	"""Opportunities raised from this Lead — where a follow-up is heading."""
	if not frappe.has_permission("Opportunity", "read"):
		return []

	return frappe.get_all(
		"Opportunity",
		filters={"opportunity_from": "Lead", "party_name": lead},
		fields=[
			"name",
			"status",
			"sales_stage",
			"transaction_date",
			"opportunity_amount",
			"currency",
			"modified",
		],
		order_by="transaction_date desc",
		limit_page_length=20,
	)


def _lead_quotations(lead):
	"""Quotations sent to this Lead."""
	if not frappe.has_permission("Quotation", "read"):
		return []

	return frappe.get_all(
		"Quotation",
		filters={"quotation_to": "Lead", "party_name": lead},
		fields=[
			"name",
			"status",
			"transaction_date",
			"valid_till",
			"grand_total",
			"currency",
			"docstatus",
			"modified",
		],
		order_by="transaction_date desc",
		limit_page_length=20,
	)


@frappe.whitelist(methods=["POST"])
def create_lead_opportunity(lead):
	"""Raise a draft Opportunity from this Lead.

	Uses ERPNext's own Lead → Opportunity mapping, so the draft carries the
	same fields Desk's "Create > Opportunity" would. An Opportunity is valid
	without items, so it can be saved here and picked up in Desk; a Quotation
	isn't, which is why that one hands straight over to the Desk form.
	"""
	_check_lead_access()
	frappe.has_permission("Opportunity", "create", throw=True)

	lead_doc = frappe.get_doc("Lead", lead)
	lead_doc.check_permission("read")

	from erpnext.crm.doctype.lead.lead import make_opportunity

	opportunity = make_opportunity(lead)
	opportunity.insert()
	return {"name": opportunity.name, "url": f"/app/opportunity/{opportunity.name}"}


@frappe.whitelist(methods=["POST"])
def add_lead_note(lead, content=None, next_follow_up_on=None):
	"""Log a call/note on a Lead and optionally (re)schedule its next follow-up.

	Notes use Lead's own native `notes` mechanism (the `CRMNote` mixin's
	`add_note`, same as the Desk form's "Notes" section) rather than a
	generic Comment or a new doctype.
	"""
	frappe.has_permission("Lead", "write", throw=True)
	doc = frappe.get_doc("Lead", lead)
	doc.check_permission("write")

	content = (content or "").strip()
	next_follow_up_on = next_follow_up_on or None
	if not content and not next_follow_up_on:
		frappe.throw(_("Enter a note or set a next follow-up date."))

	if next_follow_up_on:
		doc.custom_next_followup = next_follow_up_on

	if content:
		# add_note() (from erpnext.crm.utils.CRMNote) appends to the notes
		# child table and saves the doc, persisting the follow-up date too.
		doc.add_note(content)
	else:
		doc.save()

	return get_lead(lead)


def _window_metric(rows, start, end):
	"""Created/converted/lost counts within [start, end).

	Lead has no `converted_on`/`lost_on` timestamp, so status-change timing
	is approximated via `modified` — the closest signal stock Lead offers.
	"""
	created = [r for r in rows if start <= get_datetime(r.creation) < end]
	converted = [
		r for r in rows if r.status == CONVERTED_STATUS and start <= get_datetime(r.modified) < end
	]
	lost = [r for r in rows if r.status in LOST_STATUSES and start <= get_datetime(r.modified) < end]
	return {"created": len(created), "converted": len(converted), "lost": len(lost)}


def _followup_bucket(row, today_date):
	next_followup = row.get("custom_next_followup")
	if not next_followup:
		return "No date set"
	due = getdate(next_followup)
	if due < today_date:
		return "Overdue"
	if due == today_date:
		return "Due today"
	if due < today_date + timedelta(days=7):
		return "Due this week"
	return "Due later"


def _predicted_hours(lead_rows):
	"""Total predicted hours across these leads, and the split by month."""
	lead_names = [row.name for row in lead_rows]
	if not lead_names:
		return 0, []

	predictions = frappe.get_all(
		"Lead Hours Prediction",
		filters={"parenttype": "Lead", "parent": ("in", lead_names)},
		fields=["month_start", "hours"],
		limit_page_length=0,
	)

	by_month = {}
	total = 0
	for row in predictions:
		hours = int(row.hours or 0)
		total += hours
		if row.month_start:
			key = str(row.month_start)[:7]
			by_month[key] = by_month.get(key, 0) + hours

	monthly = [
		{"label": frappe.utils.formatdate(f"{month}-01", "MMM yyyy"), "value": hours}
		for month, hours in sorted(by_month.items())
	]
	return total, monthly


@frappe.whitelist()
def get_lead_dashboard():
	"""Return Lead pipeline KPI dashboard: follow-up backlog, trends, breakdowns."""
	_check_lead_access()

	rows = frappe.get_all(
		"Lead",
		filters={"disabled": 0},
		fields=["name", "status", "lead_owner", "creation", "modified", "custom_next_followup"],
	)

	now = now_datetime()
	current_start = now - timedelta(days=90)
	previous_start = current_start - timedelta(days=90)
	year_end = now - timedelta(days=365)
	year_start = current_start - timedelta(days=365)

	windows = {
		"current": _window_metric(rows, current_start, now),
		"previous": _window_metric(rows, previous_start, current_start),
		"year_ago": _window_metric(rows, year_start, year_end),
	}

	open_rows = [r for r in rows if _lead_bucket(r.status) == "open"]

	months = []
	cursor = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
	for offset in range(11, -1, -1):
		year = cursor.year
		month = cursor.month - offset
		while month <= 0:
			year -= 1
			month += 12
		start = cursor.replace(year=year, month=month, day=1)
		end = start.replace(year=year + 1, month=1) if month == 12 else start.replace(month=month + 1)
		metric = _window_metric(rows, start, end)
		months.append({"label": start.strftime("%b"), **metric})

	status_counts = {status: 0 for status in LEAD_STATUSES}
	for row in rows:
		if row.status in status_counts:
			status_counts[row.status] += 1

	owners = {}
	for row in open_rows:
		owner = row.lead_owner or _("Unassigned")
		owners[owner] = owners.get(owner, 0) + 1
	owner_labels = {owner: _user_label(owner) for owner in owners if owner != _("Unassigned")}

	followup_labels = ["No date set", "Overdue", "Due today", "Due this week", "Due later"]
	followup_counts = {label: 0 for label in followup_labels}
	today_date = getdate()
	for row in open_rows:
		followup_counts[_followup_bucket(row, today_date)] += 1

	predicted_total, predicted_monthly = _predicted_hours(rows)

	return {
		"windows": windows,
		"open_pipeline": len(open_rows),
		"predicted_hours": predicted_total,
		"predicted_monthly": predicted_monthly,
		"monthly": months,
		"status": [{"label": status, "value": status_counts[status]} for status in LEAD_STATUSES],
		"owners": [
			{"label": owner_labels.get(owner, owner), "value": count}
			for owner, count in sorted(owners.items(), key=lambda item: item[1], reverse=True)[:8]
		],
		"follow_up": [{"label": label, "value": followup_counts[label]} for label in followup_labels],
		"generated_at": now,
	}
