# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Readiness, CRM matching, and Lead/Contact/Address handoff for Lead Data."""

from __future__ import annotations

import re

import frappe
from frappe import _
from frappe.utils import cint, validate_email_address

from phamos.phamos.doctype.lead_data_import.services.normalization import (
	_normalize_compare_text,
)
from phamos.phamos.doctype.lead_data_import.services.web import (
	_partition_phones_and_mobiles,
	_sanitize_phone_list,
)


HANDOFF_STATUSES = (
	"Draft",
	"Needs Review",
	"Ready",
	"Possible Duplicate",
	"Linked",
	"Created",
	"Skipped",
)


def evaluate_lead_data_readiness(doc) -> dict:
	"""Return blockers, warnings, score, and suggested handoff_status (sans matches)."""
	doc = _as_lead_data_doc(doc)
	blockers = []
	warnings = []

	person = " ".join(
		part for part in (doc.first_name, doc.middle_name, doc.last_name) if part
	).strip()
	org = (doc.organization_name or "").strip()
	if not person and not org:
		blockers.append(_("Add a person name or organization name."))

	emails = _split_emails(doc.email or doc.card_email)
	phones = _sanitize_phone_list([doc.phone, doc.mobile_no])
	if not emails and not phones:
		blockers.append(_("Add at least one email or phone number."))

	for email in emails:
		try:
			validate_email_address(email, throw=True)
		except Exception:
			blockers.append(_("Email looks invalid: {0}").format(email))

	address_rows = list(doc.get("lead_data_address") or [])
	has_street = any((row.address_line_1 or "").strip() for row in address_rows)
	if not has_street and not (doc.city or "").strip():
		warnings.append(_("No postal address on the card yet."))

	if (doc.phone or "").strip() and not (doc.mobile_no or "").strip():
		warnings.append(_("Only a landline is set — mobile may still be missing."))

	secondaries = [
		row
		for row in (doc.get("lead_data_contact") or [])
		if not cint(getattr(row, "is_primary", 0))
	]
	if secondaries:
		warnings.append(
			_("Company contacts found ({0}) — review before handoff.").format(len(secondaries))
		)

	if "website_research" in (doc.lead_data or ""):
		warnings.append(_("Website research is attached — verify invented vs printed data."))

	# Score: start 100, -25 per blocker, -8 per warning
	score = max(0, 100 - 25 * len(blockers) - 8 * len(warnings))
	suggested = "Needs Review" if blockers else "Ready"

	return {
		"blockers": blockers,
		"warnings": warnings,
		"score": score,
		"suggested_status": suggested,
		"person_name": person,
		"organization_name": org,
		"emails": emails,
		"phones": phones,
	}


def find_crm_matches(doc, limit: int = 20) -> list[dict]:
	"""Rank existing Lead / Contact / Customer / Supplier matches."""
	doc = _as_lead_data_doc(doc)
	emails = _split_emails(doc.email or doc.card_email)
	phones = _sanitize_phone_list([doc.phone, doc.mobile_no])
	person = " ".join(
		part for part in (doc.first_name, doc.middle_name, doc.last_name) if part
	).strip()
	org = (doc.organization_name or "").strip()
	domain = _domain_from_url(doc.website) if doc.website else ""

	candidates: dict[tuple[str, str], dict] = {}

	def add(doctype, name, title, score, reason, extra=None):
		if not name or not frappe.db.exists(doctype, name):
			return
		key = (doctype, name)
		row = candidates.get(key)
		payload = {
			"doctype": doctype,
			"name": name,
			"title": title or name,
			"score": score,
			"reason": reason,
			"linked_parties": [],
		}
		if extra:
			payload.update(extra)
		if not row or score > row["score"]:
			candidates[key] = payload
		elif reason and reason not in (row.get("reason") or ""):
			row["reason"] = f"{row['reason']}; {reason}"
			row["score"] = max(row["score"], score)

	# --- Contact by email ---
	for email in emails:
		for contact_name in frappe.get_all(
			"Contact Email",
			filters={"email_id": email},
			pluck="parent",
			limit_page_length=10,
		):
			contact = frappe.db.get_value(
				"Contact",
				contact_name,
				["name", "first_name", "last_name", "email_id", "mobile_no", "phone", "company_name"],
				as_dict=True,
			)
			if not contact:
				continue
			title = " ".join(
				p for p in (contact.first_name, contact.last_name) if p
			) or contact.name
			add(
				"Contact",
				contact.name,
				title,
				100,
				_("Exact email {0}").format(email),
				{
					"email": contact.email_id or email,
					"phone": contact.mobile_no or contact.phone or "",
					"linked_parties": _contact_linked_parties(contact.name),
				},
			)

	# --- Contact by phone ---
	for phone in phones:
		digits = re.sub(r"\D", "", phone)
		if len(digits) < 8:
			continue
		for contact_name in frappe.get_all(
			"Contact Phone",
			filters={"phone": ["like", f"%{digits[-8:]}%"]},
			pluck="parent",
			limit_page_length=20,
		):
			contact = frappe.db.get_value(
				"Contact",
				contact_name,
				["name", "first_name", "last_name", "email_id", "mobile_no", "phone"],
				as_dict=True,
			)
			if not contact:
				continue
			contact_phones = _sanitize_phone_list(
				[contact.mobile_no, contact.phone]
				+ frappe.get_all(
					"Contact Phone",
					filters={"parent": contact.name},
					pluck="phone",
				)
			)
			if phone not in contact_phones and not any(
				re.sub(r"\D", "", p).endswith(digits[-8:]) for p in contact_phones
			):
				continue
			title = " ".join(p for p in (contact.first_name, contact.last_name) if p) or contact.name
			add(
				"Contact",
				contact.name,
				title,
				95,
				_("Exact phone {0}").format(phone),
				{
					"email": contact.email_id or "",
					"phone": phone,
					"linked_parties": _contact_linked_parties(contact.name),
				},
			)

	# --- Lead by email / phone ---
	for email in emails:
		for lead in frappe.get_all(
			"Lead",
			filters={"email_id": email},
			fields=["name", "lead_name", "company_name", "email_id", "mobile_no", "phone", "status", "customer"],
			limit_page_length=10,
		):
			add(
				"Lead",
				lead.name,
				lead.lead_name or lead.company_name or lead.name,
				90,
				_("Lead email {0}").format(email),
				{
					"email": lead.email_id or "",
					"phone": lead.mobile_no or lead.phone or "",
					"lead_status": lead.status,
					"customer": lead.customer,
					"linked_parties": _party_list_from_lead(lead),
				},
			)

	for phone in phones:
		digits = re.sub(r"\D", "", phone)
		if len(digits) < 8:
			continue
		for lead in frappe.get_all(
			"Lead",
			or_filters={
				"mobile_no": ["like", f"%{digits[-8:]}"],
				"phone": ["like", f"%{digits[-8:]}"],
			},
			fields=["name", "lead_name", "company_name", "email_id", "mobile_no", "phone", "status", "customer"],
			limit_page_length=10,
		):
			add(
				"Lead",
				lead.name,
				lead.lead_name or lead.company_name or lead.name,
				85,
				_("Lead phone match"),
				{
					"email": lead.email_id or "",
					"phone": lead.mobile_no or lead.phone or "",
					"lead_status": lead.status,
					"customer": lead.customer,
					"linked_parties": _party_list_from_lead(lead),
				},
			)

	# --- Customer / Supplier by email, phone, name, domain ---
	_match_party("Customer", "customer_name", emails, phones, org, domain, add)
	_match_party("Supplier", "supplier_name", emails, phones, org, domain, add)

	# Soft person + org against Contact
	if person and org:
		person_norm = _normalize_compare_text(person)
		org_norm = _normalize_compare_text(org)
		for contact in frappe.get_all(
			"Contact",
			filters={"company_name": ["like", f"%{org[:40]}%"]},
			fields=["name", "first_name", "last_name", "email_id", "mobile_no", "phone", "company_name"],
			limit_page_length=30,
		):
			full = " ".join(p for p in (contact.first_name, contact.last_name) if p)
			if _normalize_compare_text(full) != person_norm:
				continue
			if org_norm and _normalize_compare_text(contact.company_name or "") not in (
				org_norm,
				"",
			):
				# allow if company empty or exact-ish
				if _normalize_compare_text(contact.company_name or "") and org_norm not in _normalize_compare_text(
					contact.company_name or ""
				):
					continue
			add(
				"Contact",
				contact.name,
				full or contact.name,
				60,
				_("Same person name at organization"),
				{
					"email": contact.email_id or "",
					"phone": contact.mobile_no or contact.phone or "",
					"linked_parties": _contact_linked_parties(contact.name),
				},
			)

	ranked = sorted(candidates.values(), key=lambda r: (-r["score"], r["doctype"], r["name"]))
	return ranked[:limit]


def refresh_handoff_status(doc, commit: bool = False) -> dict:
	"""Evaluate readiness + matches and set handoff_status (unless Created/Linked/Skipped)."""
	doc = _as_lead_data_doc(doc)
	current = doc.get("handoff_status") or "Draft"
	if current in ("Created", "Linked", "Skipped"):
		return {
			"handoff_status": current,
			"readiness": evaluate_lead_data_readiness(doc),
			"matches": find_crm_matches(doc),
		}

	readiness = evaluate_lead_data_readiness(doc)
	matches = find_crm_matches(doc)
	strong = [m for m in matches if m.get("score", 0) >= 85]

	if readiness["blockers"]:
		status = "Needs Review"
	elif strong:
		status = "Possible Duplicate"
	else:
		status = "Ready"

	doc.db_set("handoff_status", status, update_modified=False)
	if commit:
		frappe.db.commit()

	result = {"handoff_status": status, "readiness": readiness, "matches": matches}
	if status == "Ready":
		auto = maybe_auto_create_crm(doc, readiness=readiness)
		if auto:
			result["auto_create"] = auto
			result["handoff_status"] = doc.get("handoff_status") or status
	return result


def maybe_auto_create_crm(doc, readiness: dict | None = None) -> dict | None:
	"""Create CRM records after enrich when score meets Phamos Settings threshold."""
	doc = _as_lead_data_doc(doc)
	if (doc.get("handoff_status") or "") != "Ready":
		return None
	if doc.get("erpnext_lead"):
		return None

	threshold = cint(
		frappe.db.get_single_value("phamos Settings", "lead_handoff_auto_create_min_score") or 95
	)
	readiness = readiness or evaluate_lead_data_readiness(doc)
	if readiness.get("blockers"):
		return None
	if cint(readiness.get("score") or 0) < threshold:
		return None

	try:
		return create_crm_records(doc.name, force=0)
	except Exception:
		frappe.log_error(
			title="Lead Data auto CRM create failed",
			message=frappe.get_traceback(),
		)
		return None


def get_improve_field_defs() -> list[dict]:
	"""Fields for the Improve & create dialog (Settings or defaults)."""
	settings = frappe.get_single("phamos Settings")
	rows = list(settings.get("lead_handoff_improve_fields") or [])
	if not rows:
		return _default_improve_fields()
	out = []
	for row in rows:
		fieldname = (row.fieldname or "").strip()
		if not fieldname:
			continue
		source = row.source_doctype or "Lead Data"
		label = (row.label or "").strip() or fieldname.replace("_", " ").title()
		out.append(
			{
				"source_doctype": source,
				"fieldname": fieldname,
				"label": label,
				"reqd": cint(row.reqd),
			}
		)
	return out or _default_improve_fields()


def _default_improve_fields() -> list[dict]:
	return [
		{"source_doctype": "Lead Data", "fieldname": "first_name", "label": "First Name", "reqd": 0},
		{"source_doctype": "Lead Data", "fieldname": "last_name", "label": "Last Name", "reqd": 0},
		{"source_doctype": "Lead Data", "fieldname": "email", "label": "Email", "reqd": 0},
		{"source_doctype": "Lead Data", "fieldname": "mobile_no", "label": "Mobile", "reqd": 0},
		{"source_doctype": "Lead Data", "fieldname": "phone", "label": "Phone", "reqd": 0},
		{"source_doctype": "Lead Data", "fieldname": "organization_name", "label": "Organization", "reqd": 0},
		{
			"source_doctype": "Lead Data Address",
			"fieldname": "address_line_1",
			"label": "Street",
			"reqd": 0,
		},
		{"source_doctype": "Lead Data Address", "fieldname": "citytown", "label": "City", "reqd": 0},
		{"source_doctype": "Lead Data Address", "fieldname": "country", "label": "Country", "reqd": 0},
	]


@frappe.whitelist()
def get_improve_form(lead_data_name: str):
	frappe.has_permission("Lead Data", doc=lead_data_name, ptype="read", throw=True)
	doc = frappe.get_doc("Lead Data", lead_data_name)
	defs = get_improve_field_defs()
	threshold = cint(
		frappe.db.get_single_value("phamos Settings", "lead_handoff_auto_create_min_score") or 95
	)
	fields = []
	for d in defs:
		value = _read_improve_field_value(doc, d["source_doctype"], d["fieldname"])
		fields.append({**d, "value": value or ""})
	review = get_handoff_review(lead_data_name)
	return {
		"fields": fields,
		"threshold": threshold,
		"handoff": review,
	}


@frappe.whitelist()
def update_lead_data_fields(lead_data_name: str, values=None, create_after: int = 1):
	"""Update configured fields from Improve dialog, refresh readiness, optionally create."""
	import json

	if isinstance(values, str):
		values = json.loads(values or "{}")
	values = values or {}
	create_after = cint(create_after)

	doc = frappe.get_doc("Lead Data", lead_data_name)
	frappe.has_permission("Lead Data", doc=doc.name, ptype="write", throw=True)

	defs = {f"{d['source_doctype']}:{d['fieldname']}": d for d in get_improve_field_defs()}
	for key, raw in values.items():
		meta = defs.get(key)
		if not meta:
			# Allow key as fieldname alone for Lead Data parent
			meta = defs.get(f"Lead Data:{key}") or {
				"source_doctype": "Lead Data",
				"fieldname": key,
				"reqd": 0,
			}
		source = meta["source_doctype"]
		fieldname = meta["fieldname"]
		value = (raw or "").strip() if isinstance(raw, str) else raw
		if meta.get("reqd") and not value:
			frappe.throw(_("{0} is required").format(meta.get("label") or fieldname))
		_write_improve_field_value(doc, source, fieldname, value)

	doc.save(ignore_permissions=False)
	frappe.db.commit()
	review = refresh_handoff_status(doc, commit=True)

	created = None
	if create_after and (doc.get("handoff_status") or "") == "Ready":
		try:
			created = create_crm_records(doc.name, force=0)
		except Exception as e:
			return {
				"ok": True,
				"updated": True,
				"handoff": get_handoff_review(doc.name),
				"create_error": str(e),
			}

	return {
		"ok": True,
		"updated": True,
		"handoff": get_handoff_review(doc.name),
		"created": created,
		"refresh": review,
	}


def _read_improve_field_value(doc, source_doctype: str, fieldname: str):
	if source_doctype == "Lead Data":
		return doc.get(fieldname)
	if source_doctype == "Lead Data Contact":
		rows = list(doc.get("lead_data_contact") or [])
		primary = next((r for r in rows if cint(getattr(r, "is_primary", 0))), None)
		row = primary or (rows[0] if rows else None)
		return row.get(fieldname) if row else ""
	if source_doctype == "Lead Data Address":
		rows = list(doc.get("lead_data_address") or [])
		return rows[0].get(fieldname) if rows else ""
	return ""


def _write_improve_field_value(doc, source_doctype: str, fieldname: str, value):
	allowed_parent = {
		"salutation",
		"first_name",
		"middle_name",
		"last_name",
		"job_title",
		"email",
		"mobile_no",
		"phone",
		"organization_name",
		"website",
		"city",
		"stateprovince",
		"country",
	}
	allowed_contact = {
		"first_name",
		"middle_name",
		"last_name",
		"email_address",
		"salutation",
		"designation",
		"phone",
		"mobile_no",
	}
	allowed_address = {
		"address_line_1",
		"address_line_2",
		"citytown",
		"stateprovince",
		"country",
		"postal_code",
		"email_address",
		"phone",
	}

	if source_doctype == "Lead Data":
		if fieldname not in allowed_parent:
			frappe.throw(_("Field {0} is not editable here").format(fieldname))
		doc.set(fieldname, value)
		return

	if source_doctype == "Lead Data Contact":
		if fieldname not in allowed_contact:
			frappe.throw(_("Field {0} is not editable here").format(fieldname))
		row = None
		for candidate in doc.get("lead_data_contact") or []:
			if cint(getattr(candidate, "is_primary", 0)):
				row = candidate
				break
		if not row:
			if doc.get("lead_data_contact"):
				row = doc.lead_data_contact[0]
			else:
				row = doc.append("lead_data_contact", {"is_primary": 1})
		row.set(fieldname, value)
		# Mirror common contact fields onto parent for readiness
		if fieldname == "email_address" and value:
			doc.email = value
		elif fieldname == "first_name":
			doc.first_name = value
		elif fieldname == "last_name":
			doc.last_name = value
		elif fieldname == "mobile_no":
			doc.mobile_no = value
		elif fieldname == "phone":
			doc.phone = value
		return

	if source_doctype == "Lead Data Address":
		if fieldname not in allowed_address:
			frappe.throw(_("Field {0} is not editable here").format(fieldname))
		if doc.get("lead_data_address"):
			row = doc.lead_data_address[0]
		else:
			row = doc.append("lead_data_address", {})
		row.set(fieldname, value)
		if fieldname == "citytown":
			doc.city = value
		elif fieldname == "country":
			doc.country = value
		elif fieldname == "stateprovince":
			doc.stateprovince = value
		return

	frappe.throw(_("Unknown source {0}").format(source_doctype))


def get_handoff_review(lead_data_name: str) -> dict:
	doc = frappe.get_doc("Lead Data", lead_data_name)
	readiness = evaluate_lead_data_readiness(doc)
	matches = find_crm_matches(doc)
	party = _summarize_party_from_matches(matches)
	threshold = cint(
		frappe.db.get_single_value("phamos Settings", "lead_handoff_auto_create_min_score") or 95
	)
	score = cint(readiness.get("score") or 0)
	status = doc.get("handoff_status") or "Draft"
	return {
		"name": doc.name,
		"handoff_status": status,
		"readiness": readiness,
		"matches": matches,
		"party_hint": party,
		"erpnext_lead": doc.get("erpnext_lead") or "",
		"erpnext_contact": doc.get("erpnext_contact") or "",
		"erpnext_address": doc.get("erpnext_address") or "",
		"erpnext_customer": doc.get("erpnext_customer") or "",
		"erpnext_supplier": doc.get("erpnext_supplier") or "",
		"auto_create_min_score": threshold,
		"needs_improve": status not in ("Created", "Skipped", "Linked")
		and (score < threshold or status == "Needs Review" or bool(readiness.get("blockers"))),
	}


@frappe.whitelist()
def create_crm_records(lead_data_name: str, force: int = 0, customer: str | None = None, supplier: str | None = None):
	"""Create Lead (+ Contact/Address) with Customer/Supplier-aware rules."""
	force = cint(force)
	doc = frappe.get_doc("Lead Data", lead_data_name)
	frappe.has_permission("Lead Data", doc=doc.name, ptype="write", throw=True)

	if doc.get("handoff_status") == "Created" and doc.get("erpnext_lead") and not force:
		return {
			"ok": True,
			"message": _("Already created"),
			"lead": doc.erpnext_lead,
			"contact": doc.get("erpnext_contact"),
			"address": doc.get("erpnext_address"),
		}

	readiness = evaluate_lead_data_readiness(doc)
	if readiness["blockers"] and not force:
		frappe.throw(
			_("Cannot create CRM records yet:\n{0}").format("\n".join(f"• {b}" for b in readiness["blockers"]))
		)

	matches = find_crm_matches(doc)
	party = _summarize_party_from_matches(matches)
	customer = (customer or party.get("customer") or "").strip()
	supplier = (supplier or party.get("supplier") or "").strip()

	strong = [m for m in matches if m.get("score", 0) >= 85]
	# Party-aware create is intentional (Converted Lead / Supplier link).
	# Otherwise require force when strong Contact/Lead duplicates exist.
	if strong and not force and not customer and not supplier:
		frappe.throw(
			_("Possible existing records found. Confirm create anyway or pick a Customer/Supplier."),
			title=_("Possible Duplicate"),
		)

	contact_name = _find_reusable_contact(matches, readiness)
	lead = _create_lead_doc(doc, readiness, customer=customer)
	created_contacts = []
	primary_contact = contact_name or ""

	payloads = _contact_payloads_from_lead_data(doc, readiness)
	for idx, payload in enumerate(payloads):
		existing = ""
		if idx == 0 and primary_contact:
			existing = primary_contact
		else:
			existing = _find_contact_for_payload(payload, matches if idx == 0 else [])
		if existing:
			_ensure_contact_links(existing, lead=lead.name, customer=customer, supplier=supplier)
			name = existing
		else:
			name = _create_contact_from_payload(payload, lead.name, customer=customer, supplier=supplier)
		if name:
			created_contacts.append(name)
			if idx == 0:
				primary_contact = name

	if not primary_contact and created_contacts:
		primary_contact = created_contacts[0]

	address_name = _create_address_doc(doc, lead.name, primary_contact, customer=customer, supplier=supplier)

	secondary_note = ""
	if len(created_contacts) > 1:
		secondary_note = "; secondary Contacts: " + ", ".join(created_contacts[1:])

	doc.db_set(
		{
			"erpnext_lead": lead.name,
			"erpnext_contact": primary_contact or "",
			"erpnext_address": address_name or "",
			"erpnext_customer": customer or "",
			"erpnext_supplier": supplier or "",
			"handoff_status": "Created",
			"findings_and_improvements": _append_finding(
				doc.get("findings_and_improvements"),
				f"Created Lead {lead.name}"
				+ (f", Contact {primary_contact}" if primary_contact else "")
				+ secondary_note
				+ (f", Customer {customer}" if customer else "")
				+ (f", Supplier {supplier}" if supplier else ""),
			),
		}
	)

	return {
		"ok": True,
		"lead": lead.name,
		"contact": primary_contact,
		"contacts": created_contacts,
		"address": address_name,
		"customer": customer,
		"supplier": supplier,
		"converted": bool(customer),
		"message": _("Lead {0} created").format(lead.name)
		+ (_(" (Converted — existing customer)") if customer else "")
		+ (
			_(" with {0} contacts").format(len(created_contacts))
			if len(created_contacts) > 1
			else ""
		),
	}


@frappe.whitelist()
def link_crm_records(
	lead_data_name: str,
	lead: str | None = None,
	contact: str | None = None,
	customer: str | None = None,
	supplier: str | None = None,
):
	"""Link Lead Data to existing CRM docs without creating a new Lead (rare path)."""
	doc = frappe.get_doc("Lead Data", lead_data_name)
	frappe.has_permission("Lead Data", doc=doc.name, ptype="write", throw=True)

	updates = {"handoff_status": "Linked"}
	if lead:
		updates["erpnext_lead"] = lead
	if contact:
		updates["erpnext_contact"] = contact
	if customer:
		updates["erpnext_customer"] = customer
	if supplier:
		updates["erpnext_supplier"] = supplier

	if contact and (lead or customer or supplier):
		_ensure_contact_links(contact, lead=lead, customer=customer, supplier=supplier)

	updates["findings_and_improvements"] = _append_finding(
		doc.get("findings_and_improvements"),
		"Linked to existing CRM records: "
		+ ", ".join(f"{k}={v}" for k, v in updates.items() if k.startswith("erpnext_") and v),
	)
	doc.db_set(updates)
	return {"ok": True, "handoff_status": "Linked", **{k: updates.get(k, "") for k in updates}}


@frappe.whitelist()
def skip_handoff(lead_data_name: str):
	doc = frappe.get_doc("Lead Data", lead_data_name)
	frappe.has_permission("Lead Data", doc=doc.name, ptype="write", throw=True)
	doc.db_set(
		{
			"handoff_status": "Skipped",
			"findings_and_improvements": _append_finding(doc.get("findings_and_improvements"), "Skipped by user"),
		}
	)
	return {"ok": True, "handoff_status": "Skipped"}


@frappe.whitelist()
def get_review_payload(lead_data_name: str):
	frappe.has_permission("Lead Data", doc=lead_data_name, ptype="read", throw=True)
	return get_handoff_review(lead_data_name)


def handoff_status_summary(lead_data_import_name: str) -> dict:
	rows = frappe.get_all(
		"Lead Data",
		filters={"lead_data_import": lead_data_import_name},
		fields=["handoff_status"],
	)
	counts = {s: 0 for s in HANDOFF_STATUSES}
	for row in rows:
		status = row.get("handoff_status") or "Draft"
		counts[status] = counts.get(status, 0) + 1
	counts["total"] = len(rows)
	return counts


# --- internals -----------------------------------------------------------------


def _as_lead_data_doc(doc):
	if isinstance(doc, str):
		return frappe.get_doc("Lead Data", doc)
	return doc


def _split_emails(value) -> list[str]:
	emails = []
	for part in re.split(r"\s*(?:,|;|\||\n)\s*", value or ""):
		email = (part or "").strip().lower()
		if email and email not in emails:
			emails.append(email)
	return emails


def _contact_linked_parties(contact_name: str) -> list[dict]:
	parties = []
	for link in frappe.get_all(
		"Dynamic Link",
		filters={"parenttype": "Contact", "parent": contact_name},
		fields=["link_doctype", "link_name"],
	):
		if link.link_doctype in ("Customer", "Supplier", "Lead"):
			parties.append({"doctype": link.link_doctype, "name": link.link_name})
	return parties


def _party_list_from_lead(lead) -> list[dict]:
	out = []
	if lead.get("customer"):
		out.append({"doctype": "Customer", "name": lead.customer})
	return out


def _match_party(doctype, name_field, emails, phones, org, domain, add):
	# email field on Customer/Supplier is optional depending on setup
	meta = frappe.get_meta(doctype)
	has_email = meta.has_field("email_id")
	for email in emails:
		filters = {}
		if has_email:
			filters["email_id"] = email
		else:
			continue
		for row in frappe.get_all(
			doctype,
			filters=filters,
			fields=["name", name_field],
			limit_page_length=10,
		):
			add(
				doctype,
				row.name,
				row.get(name_field) or row.name,
				92,
				_("{0} email {1}").format(doctype, email),
			)

	if org:
		for row in frappe.get_all(
			doctype,
			filters={name_field: ["like", f"%{org[:60]}%"]},
			fields=["name", name_field, "website"] if meta.has_field("website") else ["name", name_field],
			limit_page_length=20,
		):
			score = 70
			reason = _("{0} name similar to {1}").format(doctype, org)
			if domain and meta.has_field("website") and row.get("website"):
				party_domain = _domain_from_url(row.website)
				if party_domain and party_domain == domain:
					score = 88
					reason = _("{0} website domain {1}").format(doctype, domain)
			elif _normalize_compare_text(row.get(name_field)) == _normalize_compare_text(org):
				score = 80
				reason = _("{0} exact name").format(doctype)
			add(doctype, row.name, row.get(name_field) or row.name, score, reason)

	if domain and meta.has_field("website"):
		for row in frappe.get_all(
			doctype,
			filters={"website": ["like", f"%{domain}%"]},
			fields=["name", name_field, "website"],
			limit_page_length=10,
		):
			add(
				doctype,
				row.name,
				row.get(name_field) or row.name,
				86,
				_("{0} domain {1}").format(doctype, domain),
			)


def _summarize_party_from_matches(matches: list[dict]) -> dict:
	customer = ""
	supplier = ""
	contact = ""
	lead = ""
	for m in matches:
		if m["doctype"] == "Customer" and not customer and m["score"] >= 70:
			customer = m["name"]
		elif m["doctype"] == "Supplier" and not supplier and m["score"] >= 70:
			supplier = m["name"]
		elif m["doctype"] == "Contact" and not contact and m["score"] >= 85:
			contact = m["name"]
			for party in m.get("linked_parties") or []:
				if party.get("doctype") == "Customer" and not customer:
					customer = party["name"]
				if party.get("doctype") == "Supplier" and not supplier:
					supplier = party["name"]
		elif m["doctype"] == "Lead" and not lead and m["score"] >= 85:
			lead = m["name"]
			if m.get("customer") and not customer:
				customer = m["customer"]

	hint = ""
	if customer:
		hint = _("Existing customer {0} — new Lead will be Converted and linked.").format(customer)
	elif supplier:
		hint = _("Existing supplier {0} — new Lead will be created; Contact linked to Supplier.").format(
			supplier
		)
	elif contact or lead:
		hint = _("Existing Contact/Lead found — confirm before creating.")

	return {
		"customer": customer,
		"supplier": supplier,
		"contact": contact,
		"lead": lead,
		"message": hint,
	}


def _find_reusable_contact(matches, readiness) -> str:
	for m in matches:
		if m["doctype"] == "Contact" and m.get("score", 0) >= 85:
			return m["name"]
	return ""


def _create_lead_doc(doc, readiness, customer: str = ""):
	person = readiness.get("person_name") or ""
	first = (doc.first_name or "").strip()
	last = (doc.last_name or "").strip()
	if not first and person:
		parts = person.split(None, 1)
		first = parts[0]
		last = parts[1] if len(parts) > 1 else ""
	if not first:
		first = (doc.organization_name or _("Unknown")).strip()

	emails = readiness.get("emails") or []
	landlines, mobiles = _partition_phones_and_mobiles(
		_sanitize_phone_list([doc.phone]),
		_sanitize_phone_list([doc.mobile_no]),
	)

	lead = frappe.get_doc(
		{
			"doctype": "Lead",
			"salutation": _safe_salutation(doc.salutation),
			"first_name": first,
			"middle_name": doc.middle_name or "",
			"last_name": last,
			"job_title": doc.job_title or "",
			"email_id": emails[0] if emails else "",
			"website": doc.website or "",
			"mobile_no": mobiles[0] if mobiles else "",
			"phone": landlines[0] if landlines else "",
			"company_name": doc.organization_name or "",
			"city": doc.city or "",
			"state": doc.stateprovince or "",
			"country": _resolve_country(doc.country),
		}
	)

	if doc.get("lead_data_import") and frappe.get_meta("Lead").has_field("lead_data_import"):
		lead.lead_data_import = doc.lead_data_import

	if customer:
		lead.source = "Existing Customer"
		lead.customer = customer
		lead.status = "Converted"
	else:
		lead.status = "Lead"

	lead.insert(ignore_permissions=False)
	return lead


def _contact_payloads_from_lead_data(doc, readiness) -> list[dict]:
	"""Primary (parent) + each secondary lead_data_contact with usable identity."""
	payloads = []
	person = readiness.get("person_name") or ""
	first = (doc.first_name or "").strip() or (person.split()[0] if person else "")
	last = (doc.last_name or "").strip()
	if not last and person and " " in person:
		last = person.split(None, 1)[1]
	emails = readiness.get("emails") or []
	landlines, mobiles = _partition_phones_and_mobiles(
		_sanitize_phone_list([doc.phone]),
		_sanitize_phone_list([doc.mobile_no]),
	)
	if first or emails or mobiles or landlines or (doc.organization_name or "").strip():
		payloads.append(
			{
				"is_primary": True,
				"first_name": first or (doc.organization_name or "").strip() or _("Contact"),
				"middle_name": doc.middle_name or "",
				"last_name": last,
				"emails": emails,
				"mobiles": mobiles,
				"landlines": landlines,
				"company_name": doc.organization_name or "",
				"designation": doc.job_title or "",
				"salutation": doc.salutation or "",
			}
		)

	seen_keys = set()
	for p in payloads:
		seen_keys.add(_payload_identity_key(p))

	for row in doc.get("lead_data_contact") or []:
		if cint(getattr(row, "is_primary", 0)):
			continue
		row_first = (row.first_name or "").strip()
		row_last = (row.last_name or "").strip()
		row_emails = _split_emails(row.email_address)
		row_landlines, row_mobiles = _partition_phones_and_mobiles(
			_sanitize_phone_list([row.phone]),
			_sanitize_phone_list([row.mobile_no]),
		)
		if not (row_first or row_last or row_emails or row_mobiles or row_landlines):
			continue
		payload = {
			"is_primary": False,
			"first_name": row_first or row_last or (row_emails[0].split("@")[0] if row_emails else _("Contact")),
			"middle_name": row.middle_name or "",
			"last_name": row_last if row_first else "",
			"emails": row_emails,
			"mobiles": row_mobiles,
			"landlines": row_landlines,
			"company_name": doc.organization_name or "",
			"designation": row.designation or "",
			"salutation": row.salutation or "",
		}
		key = _payload_identity_key(payload)
		if key in seen_keys:
			continue
		seen_keys.add(key)
		payloads.append(payload)

	return payloads


def _payload_identity_key(payload: dict) -> str:
	email = (payload.get("emails") or [""])[0].lower()
	name = f"{payload.get('first_name') or ''} {payload.get('last_name') or ''}".strip().lower()
	return f"{email}|{name}"


def _find_contact_for_payload(payload: dict, matches: list) -> str:
	emails = set(payload.get("emails") or [])
	for m in matches:
		if m["doctype"] != "Contact" or m.get("score", 0) < 85:
			continue
		if emails and (m.get("email") or "").lower() in emails:
			return m["name"]
	# Exact email lookup for secondaries
	for email in emails:
		for contact_name in frappe.get_all(
			"Contact Email",
			filters={"email_id": email},
			pluck="parent",
			limit_page_length=1,
		):
			return contact_name
	return ""


def _create_contact_from_payload(payload: dict, lead_name: str, customer: str = "", supplier: str = ""):
	contact = frappe.new_doc("Contact")
	contact.first_name = payload.get("first_name") or _("Contact")
	contact.middle_name = payload.get("middle_name") or ""
	contact.last_name = payload.get("last_name") or ""
	contact.company_name = payload.get("company_name") or ""
	contact.designation = payload.get("designation") or ""
	salutation = payload.get("salutation") or ""
	if salutation and frappe.db.exists("Salutation", salutation):
		contact.salutation = salutation

	for idx, email in enumerate(payload.get("emails") or []):
		contact.append("email_ids", {"email_id": email, "is_primary": 1 if idx == 0 else 0})
	for idx, phone in enumerate(payload.get("mobiles") or []):
		contact.append("phone_nos", {"phone": phone, "is_primary_mobile_no": 1 if idx == 0 else 0})
	mobiles = payload.get("mobiles") or []
	for idx, phone in enumerate(payload.get("landlines") or []):
		contact.append(
			"phone_nos",
			{"phone": phone, "is_primary_phone": 1 if idx == 0 and not mobiles else 0},
		)

	contact.append("links", {"link_doctype": "Lead", "link_name": lead_name})
	if customer:
		contact.append("links", {"link_doctype": "Customer", "link_name": customer})
	if supplier:
		contact.append("links", {"link_doctype": "Supplier", "link_name": supplier})

	contact.insert(ignore_permissions=False)
	return contact.name


def _create_contact_doc(doc, readiness, lead_name: str, customer: str = "", supplier: str = ""):
	"""Backward-compatible single-contact create from parent fields."""
	payloads = _contact_payloads_from_lead_data(doc, readiness)
	if not payloads:
		return ""
	return _create_contact_from_payload(payloads[0], lead_name, customer=customer, supplier=supplier)


def _ensure_contact_links(contact_name: str, lead: str = "", customer: str = "", supplier: str = ""):
	contact = frappe.get_doc("Contact", contact_name)
	existing = {(l.link_doctype, l.link_name) for l in contact.links}
	changed = False
	for doctype, name in (("Lead", lead), ("Customer", customer), ("Supplier", supplier)):
		if name and (doctype, name) not in existing:
			contact.append("links", {"link_doctype": doctype, "link_name": name})
			changed = True
	if changed:
		contact.save(ignore_permissions=False)


def _create_address_doc(doc, lead_name: str, contact_name: str = "", customer: str = "", supplier: str = ""):
	rows = list(doc.get("lead_data_address") or [])
	row = None
	for candidate in rows:
		if (candidate.address_line_1 or "").strip():
			row = candidate
			break
	if not row:
		return ""

	address = frappe.new_doc("Address")
	address.address_title = (doc.organization_name or lead_name or _("Lead Address"))[:140]
	address.address_type = "Office"
	address.address_line1 = row.address_line_1 or ""
	address.address_line2 = getattr(row, "address_line_2", None) or ""
	address.city = row.citytown or doc.city or ""
	address.state = row.stateprovince or doc.stateprovince or ""
	address.pincode = row.postal_code or ""
	address.country = _resolve_country(row.country or doc.country) or "Germany"
	address.email_id = (doc.email or "").split(",")[0].strip()
	address.phone = doc.phone or doc.mobile_no or ""

	address.append("links", {"link_doctype": "Lead", "link_name": lead_name})
	if customer:
		address.append("links", {"link_doctype": "Customer", "link_name": customer})
	if supplier:
		address.append("links", {"link_doctype": "Supplier", "link_name": supplier})
	if contact_name:
		# Address→Contact link is optional; keep party links primary
		pass

	address.insert(ignore_permissions=False)
	return address.name


def _append_finding(existing, note: str) -> str:
	existing = (existing or "").strip()
	if not existing:
		return note
	if note in existing:
		return existing
	return f"{existing}\n{note}"


def _safe_salutation(value):
	value = (value or "").strip()
	if value and frappe.db.exists("Salutation", value):
		return value
	return ""


def _resolve_country(value):
	value = (value or "").strip()
	if not value:
		return ""
	if frappe.db.exists("Country", value):
		return value
	# Common aliases
	aliases = {
		"deutschland": "Germany",
		"de": "Germany",
		"germany": "Germany",
		"österreich": "Austria",
		"austria": "Austria",
		"schweiz": "Switzerland",
		"switzerland": "Switzerland",
	}
	mapped = aliases.get(value.lower())
	if mapped and frappe.db.exists("Country", mapped):
		return mapped
	# Try case-insensitive match
	found = frappe.db.get_value("Country", {"name": ["like", value]}, "name")
	return found or ""


def _domain_from_url(url):
	from urllib.parse import urlparse

	from phamos.phamos.doctype.lead_data_import.services.web import _normalize_url

	parsed = urlparse(_normalize_url(url) or "")
	domain = (parsed.netloc or "").lower()
	if domain.startswith("www."):
		domain = domain[4:]
	return domain
