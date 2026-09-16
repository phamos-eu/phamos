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


def _serialize_lead_row(row, owner_names, owner_images, today_date):
	owner = row.get("lead_owner")
	row["owner_name"] = owner_names.get(owner) or owner
	row["owner_image"] = owner_images.get(owner) or ""
	row["overdue"] = _is_overdue(row.get("custom_next_followup"), today_date)
	return row


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
	items = [_serialize_lead_row(row, owner_names, owner_images, today_date) for row in rows]

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


def _serialize_next_steps(doc):
	"""Rows of the Lead's `custom_next_steps` child table, oldest first."""
	return [
		{"name": row.name, "next_step": row.next_step, "date": row.date}
		for row in (doc.get("custom_next_steps") or [])
	]


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
		"custom_status_comment": doc.custom_status_comment,
		"qualification_status": doc.qualification_status,
		"qualified_by": doc.qualified_by,
		"qualified_by_name": _user_label(doc.qualified_by) if doc.qualified_by else None,
		"qualified_on": doc.qualified_on,
		"creation": doc.creation,
		"modified": doc.modified,
		"next_steps": _serialize_next_steps(doc),
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

	for key, value in updates.items():
		doc.set(key, value)

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

	doc.set("custom_next_steps", [])
	for row in rows or []:
		next_step = (row.get("next_step") or "").strip()
		if not next_step:
			continue
		doc.append("custom_next_steps", {"next_step": next_step, "date": row.get("date") or None})

	doc.save()
	return _serialize_next_steps(doc)


def _format_lead_activities(docinfo):
	"""Field-change (Version) and system comment entries, newest first.

	Sentence construction ("changed from X to Y") is left to the frontend —
	this just resolves each changed fieldname to its Lead form label.
	"""
	meta = frappe.get_meta("Lead")
	activities = []

	for version in docinfo.get("versions") or []:
		try:
			data = json.loads(version.get("data") or "{}")
		except (TypeError, ValueError):
			continue
		for fieldname, old, new in data.get("changed") or []:
			field = meta.get_field(fieldname)
			activities.append(
				{
					"kind": "field_change",
					"field": fieldname,
					"label": field.label if field and field.label else fieldname,
					"old": old,
					"new": new,
					"owner": version.get("owner"),
					"creation": version.get("creation"),
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

	communications = frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Lead", "reference_name": doc.name},
		fields=["name", "subject", "content", "sent_or_received", "communication_date", "sender", "recipients"],
		order_by="communication_date desc",
		limit_page_length=20,
	)

	return {
		"notes": _serialize_notes(doc),
		"communications": communications,
		"activities": _format_lead_activities(docinfo),
	}


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

	return {
		"windows": windows,
		"open_pipeline": len(open_rows),
		"monthly": months,
		"status": [{"label": status, "value": status_counts[status]} for status in LEAD_STATUSES],
		"owners": [
			{"label": owner_labels.get(owner, owner), "value": count}
			for owner, count in sorted(owners.items(), key=lambda item: item[1], reverse=True)[:8]
		],
		"follow_up": [{"label": label, "value": followup_counts[label]} for label in followup_labels],
		"generated_at": now,
	}
