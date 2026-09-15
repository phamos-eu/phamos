# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Sales Cockpit Leads API — Follow Ups list, Lead detail, notes, and pipeline KPIs."""

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from phamos.api.department_cockpit import _user_label
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

LOST_STATUSES = ("Do Not Contact", "Lost Quotation")
CONVERTED_STATUS = "Converted"


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


def _is_overdue(next_followup, now=None):
	if not next_followup:
		return False
	return get_datetime(next_followup) < (now or now_datetime())


def _serialize_lead_row(row, owner_names, now):
	row["owner_name"] = owner_names.get(row.get("lead_owner")) or row.get("lead_owner")
	row["overdue"] = _is_overdue(row.get("custom_next_followup"), now)
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

	now = now_datetime()
	items = [_serialize_lead_row(row, owner_names, now) for row in rows]

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
	communications = frappe.get_all(
		"Communication",
		filters={"reference_doctype": "Lead", "reference_name": doc.name},
		fields=["name", "subject", "content", "sent_or_received", "communication_date", "sender", "recipients"],
		order_by="communication_date desc",
		limit_page_length=10,
	)

	return {
		"name": doc.name,
		"lead_name": doc.lead_name,
		"company_name": doc.company_name,
		"status": doc.status,
		"lead_owner": doc.lead_owner,
		"lead_owner_name": _user_label(doc.lead_owner) if doc.lead_owner else None,
		"source": doc.source,
		"territory": doc.territory,
		"phone": doc.phone,
		"mobile_no": doc.mobile_no,
		"email_id": doc.email_id,
		"custom_next_followup": doc.custom_next_followup,
		"custom_status_comment": doc.custom_status_comment if doc.status == "Do Not Contact" else None,
		"creation": doc.creation,
		"modified": doc.modified,
		"notes": _serialize_notes(doc),
		"communications": communications,
		"desk_url": f"/app/lead/{doc.name}",
	}


@frappe.whitelist()
def get_lead(name):
	"""Return Lead detail for the Sales cockpit side panel."""
	frappe.has_permission("Lead", "read", throw=True)
	doc = frappe.get_doc("Lead", name)
	doc.check_permission("read")
	return _serialize_lead_detail(doc)


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


def _followup_bucket(row, now):
	next_followup = row.get("custom_next_followup")
	if not next_followup:
		return "No date set"
	due = get_datetime(next_followup)
	if due < now:
		return "Overdue"
	if due.date() == now.date():
		return "Due today"
	if due < now + timedelta(days=7):
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
	for row in open_rows:
		followup_counts[_followup_bucket(row, now)] += 1

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
