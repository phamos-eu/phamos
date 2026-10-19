# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

"""Entry points kept for the Desk form and older callers.

The work is done by the AI Accountant (phamos.ai_agents, phamos.accounting.extraction):
runs are logged as AI Agent Run, run as the AI user and only fill empty fields.
"""

import frappe
from frappe import _
from frappe.utils import cstr

from phamos.ai_agents.llm import get_mistral_settings

from .data_extract import get_extractable_fields_meta, get_extraction_key_map

DOCTYPE = "Accounting Receipt"


def _get_phamos_settings():
	"""Mistral settings {api_key, model, base_url} or None. Used by several features."""
	return get_mistral_settings()


def extract_from_pdf_and_update_ar(accounting_receipt_name):
	"""Run the AI Accountant on a receipt now. Returns {ok, reason, updated, message}."""
	from phamos.ai_agents.runner import run_now

	try:
		run = run_now(DOCTYPE, accounting_receipt_name, trigger="Manual")
	except Exception as e:
		return {"ok": False, "reason": "error", "message": str(e)}
	if run.status != "Completed":
		return {"ok": False, "reason": "error", "message": run.error, "run": run.name}
	return {"ok": True, "updated": [f.strip() for f in (run.fields_set or "").split(",") if f.strip()], "run": run.name}


def run_auto_extract_if_attachment(doc, event=None):
	"""after_insert: queue the AI Accountant when the receipt arrives with a PDF."""
	if not (doc.get("attachment") or "").lower().endswith(".pdf"):
		return
	from phamos.ai_agents.runner import enqueue_run

	enqueue_run(DOCTYPE, doc.name, trigger="Insert")


def _value_for_field_from_extracted(fieldname, extracted, key_map):
	"""Resolve value for one meta field from extracted dict (by fieldname or any key that maps to it)."""

	def norm(k):
		if not k or not isinstance(k, str):
			return None
		return cstr(k).strip().lower().replace(" ", "_").replace("-", "_")

	if not extracted:
		return None
	if fieldname in extracted and extracted[fieldname] not in (None, ""):
		return extracted[fieldname]
	for raw_key, value in extracted.items():
		if value is None or value == "":
			continue
		n = norm(raw_key)
		if key_map.get(n) == fieldname or key_map.get(raw_key) == fieldname:
			return value
	return None


def _build_review_fields(extracted):
	"""Fields for the Desk review dialog: every extractable field, filled where the AI found a value."""
	key_map = get_extraction_key_map()
	fields = []
	for meta in get_extractable_fields_meta():
		fieldname = meta["fieldname"]
		value = _value_for_field_from_extracted(fieldname, extracted, key_map)
		if value is not None and meta["fieldtype"] in ("Currency", "Float", "Int"):
			try:
				value = float(value) if not isinstance(value, (int, float)) else value
			except (ValueError, TypeError):
				pass
		if hasattr(value, "isoformat"):
			value = value.isoformat()
		fields.append(
			{
				"fieldname": fieldname,
				"label": meta["label"],
				"fieldtype": meta["fieldtype"],
				"options": meta.get("options"),
				"value": value,
			}
		)
	return fields


@frappe.whitelist()
def extract_from_pdf_for_review(accounting_receipt_name):
	"""Read the PDF and return the values for the Desk review dialog, without saving."""
	frappe.has_permission(DOCTYPE, "write", doc=accounting_receipt_name, throw=True)
	from phamos.accounting.extraction import extract_values

	doc = frappe.get_doc(DOCTYPE, accounting_receipt_name)
	try:
		extracted = extract_values(doc)
	except Exception as e:
		frappe.log_error(title=_("Data extract from PDF failed"), message=frappe.get_traceback())
		return {"ok": False, "reason": "error", "message": str(e), "hint": _("Check Error Log for details")}
	if extracted is None:
		return {"ok": False, "reason": "no_attachment"}
	extracted = {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in extracted.items()}
	return {"ok": True, "extracted": extracted, "fields": _build_review_fields(extracted)}


@frappe.whitelist()
def extract_from_pdf_now(accounting_receipt_name):
	"""Run the AI Accountant synchronously (debugging)."""
	frappe.has_permission(DOCTYPE, "write", doc=accounting_receipt_name, throw=True)
	return extract_from_pdf_and_update_ar(accounting_receipt_name)
