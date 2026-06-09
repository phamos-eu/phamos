# Copyright (c) 2025, phamos.eu and contributors
# Map extracted data (e.g. from Mistral/PDF) to Accounting Receipt fields and update the doc.

import json
import frappe
from frappe import _
from frappe.utils import getdate, flt, cstr


# Doctype to use for meta
DOCTYPE = "Accounting Receipt"

# Layout / non-data field types to skip when building extractable fields
SKIP_FIELDTYPES = {
	"Section Break", "Column Break", "Tab Break", "HTML", "Table",
	"Button", "Image", "Barcode", "Small Text",
}

# Fields we never set from extraction (system/manual only)
SKIP_FIELDNAMES = {
	"name", "owner", "creation", "modified", "modified_by",
	"docstatus", "idx", "amended_from", "attachment",
	"supplier_name",  # fetch_from supplier
	"pdf_preview", "naming_series",
	"title",  # email subject / inbox; do not overwrite from PDF or AI extract
	"is_paid",  # payment status: not from supplier PDF / AI
	"total_billing_hours",  # timesheet billing: not from supplier PDF / AI
}


def get_extractable_fields_meta():
	"""
	Return list of Accounting Receipt fields that can be updated from extracted data.
	Each item: {"fieldname": str, "label": str, "fieldtype": str, "options": str or None}
	"""
	meta = frappe.get_meta(DOCTYPE)
	out = []
	for df in meta.fields:
		if df.fieldtype in SKIP_FIELDTYPES or df.fieldname in SKIP_FIELDNAMES:
			continue
		if df.read_only or df.hidden:
			continue
		out.append({
			"fieldname": df.fieldname,
			"label": df.label or df.fieldname,
			"fieldtype": df.fieldtype,
			"options": (df.options or "").strip() or None,
		})
	return out


def get_extraction_key_map():
	"""
	Map common extraction keys (e.g. from Mistral) to Accounting Receipt fieldnames.
	Keys are normalized: lowercase, spaces -> underscores. Add aliases as needed.
	"""
	meta_list = get_extractable_fields_meta()
	key_to_field = {}
	for m in meta_list:
		fn = m["fieldname"]
		label = (m["label"] or "").strip()
		# exact fieldname
		key_to_field[fn] = fn
		# label normalized: "Supplier Reference" -> supplier_reference
		if label:
			norm = label.lower().replace(" ", "_").replace("-", "_")
			key_to_field[norm] = fn
		# common aliases for receipt extraction
	aliases = {
		"amount": "sum",
		"total": "sum",
		"total_amount": "sum",
		"date": "posting_date",
		"receipt_date": "posting_date",
		"invoice_date": "posting_date",
		"due": "due_date",
		"payment_date": "payment_date",
		"supplier_name": "supplier",  # might need resolution by name
		"vendor": "supplier",
		"reference": "supplier_reference",
		"invoice_number": "supplier_reference",
		"notes": "note",
		"description": "note",
		"billing_amount": "total_billing_amount",
		"exchange_rate": "conversion_rate",
	}
	for k, v in aliases.items():
		if v in [x["fieldname"] for x in meta_list]:
			key_to_field[k] = v
	return key_to_field


def _normalize_extraction_key(key):
	if not key or not isinstance(key, str):
		return None
	return key.strip().lower().replace(" ", "_").replace("-", "_")


def _parse_german_number(value):
	"""
	Normalize a German-locale number string to a plain decimal string before flt().
	German format: period = thousands separator, comma = decimal separator.
	  "520,03"   -> "520.03"
	  "1.234,56" -> "1234.56"
	  "437,00"   -> "437.00"
	Non-string or already-numeric values pass through unchanged.
	"""
	if not isinstance(value, str):
		return value
	v = value.strip()
	if "," in v and "." in v:
		# e.g. "1.234,56" — period is thousands separator
		v = v.replace(".", "").replace(",", ".")
	elif "," in v:
		# e.g. "520,03" — comma is decimal separator (not thousands)
		# Only treat as decimal if digits after comma look like cents (1-2 digits)
		parts = v.split(",")
		if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) <= 2:
			v = v.replace(",", ".")
		else:
			# comma as thousands separator (e.g. "1,234") — strip it
			v = v.replace(",", "")
	return v


def _set_value_for_field(doc, fieldname, value, meta):
	"""Set one field on doc from extracted value. Validates type and Link existence."""
	if value is None or (isinstance(value, str) and not value.strip()):
		return False
	fieldtype = meta.get("fieldtype")
	options = meta.get("options")

	if fieldtype == "Link" and options:
		# value should be a doc name; optionally resolve by name later
		name = cstr(value).strip()
		if not frappe.db.exists(options, name):
			# try match by name/title if the doctype has such a field
			cand = _resolve_link_by_name(options, name)
			if cand:
				doc.set(fieldname, cand)
				return True
			return False
		doc.set(fieldname, name)
		return True

	if fieldtype == "Date":
		try:
			doc.set(fieldname, getdate(value))
			return True
		except Exception:
			return False

	if fieldtype in ("Currency", "Float", "Int"):
		try:
			doc.set(fieldname, flt(_parse_german_number(value)))
			return True
		except Exception:
			return False

	if fieldtype == "Check":
		doc.set(fieldname, 1 if value in (True, 1, "1", "yes", "true", "y") else 0)
		return True

	if fieldtype == "Select" and options:
		opts = [o.strip() for o in (options or "").split("\n") if o.strip()]
		val = cstr(value).strip()
		if val in opts:
			doc.set(fieldname, val)
			return True
		# case-insensitive match
		for o in opts:
			if o.lower() == val.lower():
				doc.set(fieldname, o)
				return True
		return False

	# Data, Text, Text Editor, etc.
	doc.set(fieldname, cstr(value).strip() if value is not None else "")
	return True


def _resolve_link_by_name(doctype, name_or_title):
	"""Try to find a doc by name or by a 'name' / 'title' / 'supplier_name' like field."""
	if frappe.db.exists(doctype, name_or_title):
		return name_or_title
	meta = frappe.get_meta(doctype)
	# common display fields
	for field in ("supplier_name", "customer_name", "title", "company_name"):
		if meta.has_field(field):
			found = frappe.db.get_value(doctype, {field: ["like", f"%{name_or_title}%"]}, "name")
			if found:
				return found
	# match name with like
	found = frappe.db.get_value(doctype, {"name": ["like", f"%{name_or_title}%"]}, "name")
	return found


def update_accounting_receipt_from_extracted(accounting_receipt_name, extracted_data):
	"""
	Compare extracted_data (dict from Mistral) with Accounting Receipt meta and update
	only matching, valid fields. Keys in extracted_data can be fieldnames or labels
	(or aliases from get_extraction_key_map).

	:param accounting_receipt_name: Name of the Accounting Receipt doc
	:param extracted_data: dict, e.g. {"supplier": "Acme", "sum": 100, "posting_date": "2025-01-15"}
	:return: dict with "updated": list of fieldnames set, "skipped": list of keys not mapped/set
	"""
	if not extracted_data or not isinstance(extracted_data, dict):
		return {"updated": [], "skipped": list(extracted_data.keys()) if isinstance(extracted_data, dict) else []}

	doc = frappe.get_doc(DOCTYPE, accounting_receipt_name)
	key_map = get_extraction_key_map()
	meta_by_field = {m["fieldname"]: m for m in get_extractable_fields_meta()}

	updated = []
	skipped = []

	for raw_key, value in extracted_data.items():
		norm = _normalize_extraction_key(cstr(raw_key))
		fieldname = key_map.get(norm) or key_map.get(raw_key)
		if not fieldname or fieldname not in meta_by_field:
			skipped.append(raw_key)
			continue
		meta = meta_by_field[fieldname]
		try:
			if _set_value_for_field(doc, fieldname, value, meta):
				updated.append(fieldname)
			else:
				skipped.append(raw_key)
		except Exception:
			skipped.append(raw_key)

	if updated:
		doc.flags.ignore_validate_update_after_submit = True
		doc.save(ignore_permissions=True)

	return {"updated": updated, "skipped": skipped}


def get_extraction_schema_for_prompt():
	"""
	Return a simple schema (list of field labels and types) so you can ask Mistral
	to extract from PDF and return a JSON with these keys. Uses labels as keys
	for readability in the prompt.
	"""
	meta_list = get_extractable_fields_meta()
	return [
		{"key": m["label"].replace(" ", "_").lower(), "label": m["label"], "fieldtype": m["fieldtype"], "fieldname": m["fieldname"]}
		for m in meta_list
	]


@frappe.whitelist()
def get_accounting_receipt_extraction_meta():
	"""API: Return extractable fields meta and key map for building Mistral prompts."""
	return {
		"fields": get_extractable_fields_meta(),
		"key_map": get_extraction_key_map(),
		"schema_for_prompt": get_extraction_schema_for_prompt(),
	}


def resolve_link_for_extract(doctype, value):
	"""
	Resolve extracted value to a doc name for Link fields.
	Returns the doc name if value matches the doc's name or its display name field
	(supplier_name, company_name, cost_center_name, customer_name). Exact match only.
	"""
	if not value or not isinstance(value, str) or not doctype:
		return None
	value = cstr(value).strip()
	if not value:
		return None
	if frappe.db.exists(doctype, value):
		return value
	meta = frappe.get_meta(doctype)
	for field in ("supplier_name", "customer_name", "company_name", "cost_center_name", "title"):
		if meta.has_field(field):
			name = frappe.db.get_value(doctype, {field: value}, "name")
			if name:
				return name
	return None


@frappe.whitelist()
def resolve_link_values(link_list):
	"""
	Resolve multiple link values for the review dialog.
	link_list: list of { "fieldname", "doctype", "value" }.
	Returns dict of fieldname -> resolved doc name (or None if not found).
	"""
	if isinstance(link_list, str):
		link_list = json.loads(link_list or "[]")
	out = {}
	for item in (link_list or []):
		fieldname = item.get("fieldname")
		doctype = item.get("doctype")
		value = item.get("value")
		if fieldname and doctype and value:
			out[fieldname] = resolve_link_for_extract(doctype, value)
	return out


@frappe.whitelist()
def apply_extracted_data(accounting_receipt_name, extracted_data):
	"""
	API: Apply extracted key-value data to an Accounting Receipt.
	extracted_data can be a JSON string or dict.
	"""
	if isinstance(extracted_data, str):
		extracted_data = json.loads(extracted_data)
	return update_accounting_receipt_from_extracted(accounting_receipt_name, extracted_data)


def _normalize_extracted_key(key):
	"""Normalize a key from extracted data (e.g. from Mistral) for lookup."""
	if not key or not isinstance(key, str):
		return None
	return key.strip().lower().replace(" ", "_").replace("-", "_")


@frappe.whitelist()
def create_address_for_supplier(supplier, address_data):
	"""
	Create an Address from extracted address_data and link it to the Supplier.
	address_data can be a JSON string or dict with keys like address_line1, address_line2,
	city, state, country, pincode (any key normalized to these names).
	Returns the new Address name or None if no address fields present.
	"""
	if not supplier or not frappe.db.exists("Supplier", supplier):
		return None
	if isinstance(address_data, str):
		address_data = json.loads(address_data or "{}")
	if not address_data or not isinstance(address_data, dict):
		return None

	norm = _normalize_extracted_key
	def get_val(*keys):
		for k in keys:
			for raw, v in (address_data or {}).items():
				if v is None or (isinstance(v, str) and not v.strip()):
					continue
				if norm(raw) == k or raw == k:
					return cstr(v).strip()
		return None

	address_line1 = get_val("address_line1")
	city = get_val("city")
	country = get_val("country")
	if not address_line1 and not city and not country:
		return None

	addr = frappe.new_doc("Address")
	addr.address_type = "Billing"
	addr.address_line1 = address_line1 or "-"
	addr.address_line2 = get_val("address_line2") or ""
	addr.city = city or "-"
	addr.state = get_val("state") or ""
	addr.country = country or frappe.db.get_single_value("System Settings", "country") or ""
	addr.pincode = get_val("pincode") or ""
	addr.append("links", {"link_doctype": "Supplier", "link_name": supplier})
	addr.insert(ignore_permissions=True)
	# Set as primary address on Supplier so it shows in supplier_primary_address field
	try:
		frappe.db.set_value("Supplier", supplier, "supplier_primary_address", addr.name, update_modified=False)
		frappe.db.commit()
	except Exception:
		pass
	return addr.name


@frappe.whitelist()
def create_supplier_with_address(supplier_name, address_data, tax_category=None):
	"""
	Create a Supplier and optionally an Address from extracted data.
	supplier_name: required. tax_category: required for new Supplier (Link to Tax Category).
	address_data: optional dict with address_line1, city, country, etc.
	Returns the new Supplier name. If supplier_name already exists (by name or supplier_name), returns that.
	"""
	if not supplier_name or not cstr(supplier_name).strip():
		return None
	supplier_name = cstr(supplier_name).strip()
	# Reuse existing if match by name or supplier_name
	existing = resolve_link_for_extract("Supplier", supplier_name)
	if existing:
		# If we have address data and supplier has no primary address, create and link
		if isinstance(address_data, str):
			address_data = json.loads(address_data or "{}")
		if address_data and isinstance(address_data, dict):
			primary = frappe.db.get_value("Supplier", existing, "supplier_primary_address")
			if not primary and _has_address_data(address_data):
				create_address_for_supplier(existing, address_data)
		return existing
	# Create new Supplier (Tax Category is mandatory on Supplier)
	if not tax_category or not cstr(tax_category).strip():
		frappe.throw(_("Tax Category is required to create a Supplier."))
	if not frappe.db.exists("Tax Category", tax_category):
		frappe.throw(_("Invalid Tax Category: {0}").format(tax_category))
	supp = frappe.new_doc("Supplier")
	supp.supplier_name = supplier_name
	supp.tax_category = cstr(tax_category).strip()
	supp.insert(ignore_permissions=True)
	name = supp.name
	if address_data:
		if isinstance(address_data, str):
			address_data = json.loads(address_data or "{}")
		if isinstance(address_data, dict) and _has_address_data(address_data):
			create_address_for_supplier(name, address_data)
	return name


def _has_address_data(address_data):
	"""True if address_data has at least one of address_line1, city, country."""
	if not address_data or not isinstance(address_data, dict):
		return False
	norm = _normalize_extracted_key
	for k in ("address_line1", "city", "country"):
		for raw, v in address_data.items():
			if v is None or (isinstance(v, str) and not v.strip()):
				continue
			if norm(raw) == k or raw == k:
				return True
	return False
