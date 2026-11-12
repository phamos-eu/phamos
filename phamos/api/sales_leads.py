# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Leads API: Follow Ups list, Lead detail, notes and activity."""

import ipaddress
import json
import re
import socket
from urllib.parse import urlparse

import frappe
import requests
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_url, getdate, now_datetime
from frappe.utils.html_utils import clean_email_html

from phamos.api.department_cockpit import _user_images, _user_label, role_shortlist_users

LEAD_ROLES = ("System Manager", "Sales Manager", "Sales User")

# ERPNext's Lead status options. On develop this list lives in the Sales Action
# Panel page, which version-15 does not have.
LEAD_STATUSES = [
	"Lead",
	"Open",
	"Replied",
	"Opportunity",
	"Quotation",
	"Lost Quotation",
	"Interested",
	"Converted",
	"Do Not Contact",
]

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
	"source",
	"custom_lead_direction",
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
	"custom_lead_direction",
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

WEBSITE_CHECK_TIMEOUT = 5
# Enough for the usual http→https→www chain, few enough to stop a redirect loop.
WEBSITE_CHECK_MAX_HOPS = 4
# Only the web's own ports: anything else turns the check into a port scanner.
WEBSITE_CHECK_PORTS = (None, 80, 443)
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

	Limitation: `requests` resolves the host again when it fetches, so a DNS
	record that changes between the two lookups (DNS rebinding) is not caught.
	The check only reads response headers, which bounds what that could leak.
	"""
	parsed = urlparse(url)
	if parsed.scheme not in ("http", "https"):
		return False
	if not parsed.hostname:
		return False
	try:
		if parsed.port not in WEBSITE_CHECK_PORTS:
			return False
	except ValueError:
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
		# is_global also excludes shared address space (100.64.0.0/10), which
		# is_private does not, and where some cloud metadata services live.
		if not ip.is_global or ip.is_multicast:
			return False

	return True


def _frame_ancestors_allow_embedding(csp_header):
	"""True unless a frame-ancestors directive rules this site out.

	Only a wildcard (or a bare `https:`) source is treated as embeddable —
	'none'/'self'/an explicit host list all mean our cockpit can't frame it.
	"""
	if not csp_header:
		return True

	# Several CSP headers arrive joined by commas; each one must allow framing.
	for directive in re.split(r"[;,]", csp_header):
		parts = directive.strip().split()
		if not parts or parts[0].lower() != "frame-ancestors":
			continue
		sources = [p.strip().lower() for p in parts[1:]]
		return any(source in ("*", "https:", "http:") for source in sources)

	return True


def _is_own_site(url):
	"""True when the URL points at this Frappe site itself.

	The website dialog's iframe allows scripts and same-origin, which is only
	safe while the framed page is on another origin.
	"""
	own_host = (urlparse(get_url()).hostname or "").lower()
	return bool(own_host) and (urlparse(url).hostname or "").lower() == own_host


@frappe.whitelist()
@rate_limit(limit=60, seconds=60 * 60)
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

	try:
		response, final_url = _fetch_for_embedding(normalized)
	except requests.RequestException:
		return {"url": normalized, "embeddable": False, "reason": "unreachable"}

	if response is None:
		return {"url": normalized, "embeddable": False, "reason": "unreachable"}

	if response.status_code >= 400:
		return {"url": final_url, "embeddable": False, "reason": "unreachable"}

	if _is_own_site(final_url):
		return {"url": final_url, "embeddable": False, "reason": "blocked"}

	x_frame_options = (response.headers.get("X-Frame-Options") or "").strip().lower()
	if x_frame_options:
		return {"url": final_url, "embeddable": False, "reason": "blocked"}

	if not _frame_ancestors_allow_embedding(response.headers.get("Content-Security-Policy")):
		return {"url": final_url, "embeddable": False, "reason": "blocked"}

	return {"url": final_url, "embeddable": True, "reason": ""}


def _fetch_for_embedding(url):
	"""Fetch a URL for the embeddability check, validating every hop.

	Redirects are followed by hand rather than by requests: letting requests
	follow them means the redirected request is already made by the time the
	final URL can be checked, so a public host redirecting to an internal one
	would be fetched first and only judged afterwards.
	"""
	headers = {"User-Agent": WEBSITE_CHECK_USER_AGENT}
	current = url

	for _hop in range(WEBSITE_CHECK_MAX_HOPS):
		if not _is_public_http_url(current):
			return None, current

		response = requests.head(
			current, timeout=WEBSITE_CHECK_TIMEOUT, allow_redirects=False, headers=headers
		)
		if response.status_code in (405, 501) or response.status_code >= 400:
			# Plenty of sites don't answer HEAD properly; fall back to GET.
			response = requests.get(
				current,
				timeout=WEBSITE_CHECK_TIMEOUT,
				allow_redirects=False,
				headers=headers,
				stream=True,
			)
			response.close()

		if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
			location = response.headers.get("Location")
			if not location:
				return response, current
			current = requests.compat.urljoin(current, location)
			continue

		return response, current

	return None, current


def _check_lead_access():
	"""Raise unless the user can read Lead and holds a Sales role."""
	frappe.has_permission("Lead", "read", throw=True)
	if frappe.session.user == "Administrator":
		return
	if not set(frappe.get_roles()) & set(LEAD_ROLES):
		frappe.throw(_("You need a Sales role to use the Leads cockpit."), frappe.PermissionError)


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


def _overview_filters(created_from, created_to, direction, source, status):
	"""Validated `get_list` filters for a figure of the lead overview; "none" means "not set"."""
	from phamos.api.sales_lead_overview import NOT_SET, validate_direction
	from phamos.marketing.defaults import LEAD_DIRECTION_FIELD

	filters = []
	if created_from:
		filters.append(["creation", ">=", f"{getdate(created_from)} 00:00:00"])
	if created_to:
		filters.append(["creation", "<=", f"{getdate(created_to)} 23:59:59.999999"])
	direction = validate_direction(direction)
	if direction:
		filters.append([LEAD_DIRECTION_FIELD, "is", "not set"] if direction == NOT_SET else [LEAD_DIRECTION_FIELD, "=", direction])
	if source:
		filters.append(["source", "is", "not set"] if source == NOT_SET else ["source", "=", source])
	if status == NOT_SET:
		filters.append(["status", "is", "not set"])
	elif status:
		if status not in LEAD_STATUSES:
			frappe.throw(_("Unknown Lead status: {0}").format(status))
		filters.append(["status", "=", status])
	return filters


@frappe.whitelist()
def get_leads(created_from=None, created_to=None, direction=None, source=None, status=None):
	"""Return Leads for the list, sorted for follow-up triage.

	Without filters: every non-disabled Lead. Leads with no `custom_next_followup` sort first (need triage),
	then dated ones, ascending — MariaDB sorts NULL first under `IS NULL ... DESC`.

	With a filter from the lead overview (phamos/phamos#1758): exactly the leads its figure counted —
	disabled ones included, since the overview counts every lead that came in — newest first.
	"""
	_check_lead_access()
	overview_filters = _overview_filters(created_from, created_to, direction, source, status)

	# get_list, not get_all: User Permissions (e.g. a Territory restriction)
	# must narrow the list just as they narrow Desk's.
	rows = frappe.get_list(
		"Lead",
		filters=overview_filters or {"disabled": 0},
		fields=LEAD_LIST_FIELDS,
		order_by="creation desc" if overview_filters else "custom_next_followup is null desc, custom_next_followup asc",
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


def _serialize_lead_detail(doc):
	"""Identity, master-data and transactional fields of a Lead.

	Notes and Communications are heavier and only needed by the feed, so
	`get_lead_activity` serves them separately.
	"""
	return {
		"name": doc.name,
		# Master data: company/contact identity and firmographics.
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
		# Who last changed the comment and when — Desk shows this alongside the
		# comment, so the cockpit shouldn't be the surface that drops it.
		"custom_status_comment_modified_by": doc.custom_status_comment_modified_by,
		"custom_status_comment_modified_by_name": _user_label(doc.custom_status_comment_modified_by)
		if doc.custom_status_comment_modified_by
		else None,
		"custom_status_comment_modified_date": doc.custom_status_comment_modified_date,
		"qualification_status": doc.qualification_status,
		"custom_lead_direction": doc.get("custom_lead_direction"),
		"qualified_by": doc.qualified_by,
		"qualified_by_name": _user_label(doc.qualified_by) if doc.qualified_by else None,
		"qualified_on": doc.qualified_on,
		"creation": doc.creation,
		"modified": doc.modified,
		"desk_url": f"/app/lead/{doc.name}",
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def lead_owner_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search for Lead Owner: Sales-role users first, then anyone else.

	PM decision (#1757): the suggestions are the sales team, but a lead can
	still be given to any enabled system user.
	"""
	_check_lead_access()
	sales_users = {u["name"] for u in role_shortlist_users(LEAD_ROLES, limit=500)}
	like = f"%{txt or ''}%"
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User", "name": ("!=", "Guest")},
		or_filters={"name": ("like", like), "full_name": ("like", like)},
		fields=["name", "full_name"],
		order_by="full_name asc",
		limit_page_length=500,
	)
	users.sort(key=lambda u: u.name not in sales_users)
	start = int(start or 0)
	return [(u.name, u.full_name) for u in users[start : start + int(page_len or 20)]]


@frappe.whitelist()
def get_lead(name):
	"""Return Lead master + transactional data for the Sales cockpit detail view."""
	_check_lead_access()
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
	custom_lead_direction=None,
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
	_check_lead_access()
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
		"custom_lead_direction": custom_lead_direction,
	}
	updates = {k: v for k, v in fields.items() if v is not None}
	unknown = set(updates) - set(LEAD_EDITABLE_FIELDS)
	if unknown:
		frappe.throw(_("Invalid Lead field(s): {0}").format(", ".join(sorted(unknown))))
	if not updates:
		frappe.throw(_("No fields to update"))

	# Same as the Desk form: a source with a default direction fills an empty direction; a chosen one wins
	# (phamos/phamos#574).
	if updates.get("source") and "custom_lead_direction" not in updates and not doc.get("custom_lead_direction"):
		from phamos.marketing.crm import lead_source_direction

		direction = lead_source_direction(updates["source"])
		if direction:
			updates["custom_lead_direction"] = direction

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

	doc.save()
	result = get_lead(name)
	result["conflict"] = conflict
	return result


def _field_label(meta, fieldname):
	field = meta.get_field(fieldname)
	return _(field.label) if field and field.label else fieldname


def _display_value(meta, fieldname, value):
	"""Select values (status, qualification) are English options; translate them."""
	field = meta.get_field(fieldname)
	if value and field and field.fieldtype == "Select":
		return _(str(value))
	return value


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
		filters={
			"reference_doctype": "Lead",
			"reference_name": lead,
			"communication_type": "Communication",
		},
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
			filters={"name": ("in", unseen), "communication_type": "Communication"},
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


@frappe.whitelist(methods=["POST"])
def update_lead_note(lead, note_name, content):
	"""Edit an existing note on a Lead.

	Uses ERPNext's own `CRMNote.edit_note` (the mechanism behind the Desk
	form's note editing) rather than writing the child row directly, so
	both paths behave the same.
	"""
	_check_lead_access()
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
	this resolves each changed fieldname to its translated Lead form label.
	Child table rows (e.g. notes) come through Version's added/removed/
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
					"old": _display_value(meta, fieldname, old),
					"new": _display_value(meta, fieldname, new),
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

	owners = {a["owner"] for a in activities if a.get("owner")}
	owner_names = {owner: _user_label(owner) for owner in owners}
	for activity in activities:
		activity["owner_name"] = owner_names.get(activity.get("owner")) or activity.get("owner")

	activities.sort(key=lambda a: a.get("creation") or "", reverse=True)
	return activities


@frappe.whitelist()
def get_lead_activity(name):
	"""Return Communications and change/comment Activities for a Lead.

	Notes come from Lead's own `notes` child table via `_serialize_notes`.
	Activities are built from
	Frappe's own `get_docinfo` — the same aggregation the Desk form's
	timeline uses — for Versions and system comments, rather than
	re-deriving Version-diff parsing by hand; Communications keep the
	existing direct query since `get_docinfo`'s own field selection for
	them isn't guaranteed to include everything the feed wants (e.g.
	`sent_or_received`).
	"""
	_check_lead_access()
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
	}


@frappe.whitelist(methods=["POST"])
def add_lead_note(lead, content=None, next_follow_up_on=None):
	"""Log a call/note on a Lead and optionally (re)schedule its next follow-up.

	Notes use Lead's own native `notes` mechanism (the `CRMNote` mixin's
	`add_note`, same as the Desk form's "Notes" section) rather than a
	generic Comment or a new doctype.
	"""
	_check_lead_access()
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
