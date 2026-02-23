# Copyright (c) 2025, phamos.eu and contributors
# Extract data from Accounting Receipt PDF attachment via Mistral OCR + chat and update the doc.

import base64
import json
import os

import frappe
from frappe import _
from frappe.utils import cstr, get_files_path

from .data_extract import (
	get_extraction_key_map,
	get_extractable_fields_meta,
	get_extraction_schema_for_prompt,
	update_accounting_receipt_from_extracted,
)

MISTRAL_OCR_MODEL = "mistral-ocr-latest"
# Chat model: must be a chat/completion model, NOT an OCR model
MISTRAL_CHAT_MODEL_DEFAULT = "mistral-small-latest"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
MISTRAL_OCR_BASE_URL = "https://api.mistral.ai/v1"


def _get_phamos_settings():
	"""Return Mistral config from Phamos Settings. Returns None if not configured."""
	try:
		settings = frappe.get_single("phamos Settings")
		# Password field is encrypted in DB; must use get_password() for the real key
		api_key = settings.get_password("mistral_api_key") if settings.get("mistral_api_key") else None
		if not api_key or not api_key.strip():
			return None
		return {
			"api_key": api_key.strip(),
			"model": getattr(settings, "mistral_model", None) or "mistral-small-latest",
			"base_url": (getattr(settings, "mistral_base_url", None) or "").strip() or MISTRAL_BASE_URL,
		}
	except Exception:
		return None


def _get_pdf_path_from_attachment(attachment_file_url):
	"""
	Resolve attachment file_url (e.g. /files/xxx.pdf or /private/files/xxx.pdf) to filesystem path.
	Returns None if not found or not a file.
	"""
	if not attachment_file_url or not attachment_file_url.strip():
		return None
	url = attachment_file_url.strip()
	# Handle full URL (e.g. https://site/files/xxx.pdf) - take path after host
	if "://" in url:
		from urllib.parse import urlparse
		url = urlparse(url).path or url
	if not url.lower().endswith(".pdf"):
		return None
	# Normalize: remove leading slash
	url = url.lstrip("/")
	if url.startswith("private/files/"):
		rest = url.replace("private/files/", "", 1)
		path = get_files_path(*rest.split("/"), is_private=1)
	elif url.startswith("files/"):
		rest = url.replace("files/", "", 1)
		path = get_files_path(*rest.split("/"))
	else:
		# Just filename
		path = get_files_path(url)
	if path and os.path.isfile(path):
		return path
	return None


def _read_pdf_as_base64(pdf_path):
	"""Read PDF file and return base64 string."""
	with open(pdf_path, "rb") as f:
		return base64.b64encode(f.read()).decode("utf-8")


def _call_mistral_ocr(api_key, base_url, pdf_base64):
	"""Call Mistral OCR API; return markdown text from the document."""
	import requests

	url = f"{base_url.rstrip('/')}/ocr"
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}
	payload = {
		"model": MISTRAL_OCR_MODEL,
		"document": {
			"type": "document_url",
			"document_url": f"data:application/pdf;base64,{pdf_base64}",
		},
	}
	resp = requests.post(url, json=payload, headers=headers, timeout=120)
	if not resp.ok:
		body = resp.text[:500] if resp.text else ""
		raise Exception(f"Mistral OCR failed ({resp.status_code}): {body}")
	data = resp.json()
	# Response has pages[].markdown; concatenate
	markdown_parts = []
	for page in data.get("pages") or []:
		markdown_parts.append(page.get("markdown") or "")
	return "\n\n".join(markdown_parts)


def _call_mistral_chat_extract(api_key, base_url, model, document_markdown):
	"""Ask Mistral to return a JSON object with Accounting Receipt fields from the document text."""
	import requests

	# OCR models (e.g. mistral-ocr-latest) are not valid for Chat API; use a chat model
	if not model or "ocr" in (model or "").lower():
		model = MISTRAL_CHAT_MODEL_DEFAULT

	schema = get_extraction_schema_for_prompt()
	field_list = ", ".join([f'"{m["key"]}" (for {m["label"]})' for m in schema])
	address_keys = "address_line1, address_line2, city, state, country, pincode"

	prompt = f"""You are extracting structured data from a receipt/invoice document. The following text was extracted from a PDF via OCR.

Return a JSON object with keys matching these field names (use the key in quotes): {field_list}.
If the document contains a vendor/supplier address, also include these optional keys: {address_keys}.
Use only the keys listed (plus the optional address keys when present). For dates use YYYY-MM-DD. For numbers use digits (no currency symbols). For missing values omit the key.
Output nothing else except the JSON object.

Document text:
---
{document_markdown[:12000]}
---"""

	url = f"{base_url.rstrip('/')}/chat/completions"
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
	}
	payload = {
		"model": model,
		"messages": [{"role": "user", "content": prompt}],
		"response_format": {"type": "json_object"},
	}
	resp = requests.post(url, json=payload, headers=headers, timeout=60)
	if not resp.ok:
		body = resp.text[:500] if resp.text else ""
		raise Exception(f"Mistral Chat failed ({resp.status_code}): {body}")
	data = resp.json()
	content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
	return json.loads(content)


def extract_from_pdf_and_update_ar(accounting_receipt_name):
	"""
	Main entry: get Accounting Receipt attachment, run Mistral OCR + chat, apply extracted data.
	Called from hook or background job. Logs errors; does not raise.
	"""
	try:
		doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
		attachment_url = doc.get("attachment")
		if not attachment_url:
			return {"ok": False, "reason": "no_attachment"}

		pdf_path = _get_pdf_path_from_attachment(attachment_url)
		if not pdf_path:
			frappe.log_error(
				title=_("Data extract: PDF path not found"),
				message=f"attachment={attachment_url}",
			)
			return {"ok": False, "reason": "pdf_not_found"}

		settings = _get_phamos_settings()
		if not settings:
			frappe.log_error(
				title=_("Data extract: Mistral not configured"),
				message="Phamos Settings > Data Extract: set Mistral API Key",
			)
			return {"ok": False, "reason": "mistral_not_configured"}

		pdf_b64 = _read_pdf_as_base64(pdf_path)
		# Use same base URL as Chat when set (e.g. proxy); else default OCR endpoint
		ocr_base = (settings.get("base_url") or "").strip() or MISTRAL_OCR_BASE_URL
		if not ocr_base.endswith("/v1"):
			ocr_base = ocr_base.rstrip("/") + "/v1" if ocr_base else MISTRAL_OCR_BASE_URL
		markdown = _call_mistral_ocr(
			settings["api_key"],
			ocr_base,
			pdf_b64,
		)
		if not (markdown or "").strip():
			return {"ok": False, "reason": "ocr_empty"}

		extracted = _call_mistral_chat_extract(
			settings["api_key"],
			settings["base_url"],
			settings["model"],
			markdown,
		)
		result = update_accounting_receipt_from_extracted(accounting_receipt_name, extracted)
		return {"ok": True, "updated": result.get("updated", []), "skipped": result.get("skipped", [])}
	except Exception as e:
		tb = frappe.get_traceback()
		frappe.log_error(title=_("Data extract from PDF failed"), message=tb)
		msg = str(e)
		# Explain DNS/network errors so user knows it's environment, not config
		if "nodename nor servname" in msg or "Failed to resolve" in msg or "NameResolutionError" in msg or "ConnectionError" in type(e).__name__ or isinstance(e, OSError):
			msg = _("Cannot reach Mistral API (network/DNS error). Check: 1) Internet connection, 2) DNS can resolve api.mistral.ai, 3) Firewall allows HTTPS to Mistral. If you use a proxy, set Base URL in Phamos Settings > Data Extract.")
		return {"ok": False, "reason": "error", "message": msg, "traceback": tb}


def run_auto_extract_if_attachment(doc, event=None):
	"""
	Call from Accounting Receipt after_insert / on_update.
	If attachment is set (and changed on update), enqueue extraction so fields auto-update.
	"""
	if not doc.get("attachment"):
		return
	# On update: only run if attachment just changed
	if event == "on_update":
		old = doc.get_doc_before_save()
		if old and old.get("attachment") == doc.get("attachment"):
			return
	frappe.enqueue(
		extract_from_pdf_and_update_ar,
		queue="default",
		timeout=300,
		accounting_receipt_name=doc.name,
		enqueue_after_commit=True,
	)


def _extract_from_pdf_only(accounting_receipt_name):
	"""
	Run OCR + Mistral chat and return extracted dict. Does NOT update the doc.
	Returns (extracted_dict, None) on success or (None, error_result_dict) on failure.
	"""
	doc = frappe.get_doc("Accounting Receipt", accounting_receipt_name)
	attachment_url = doc.get("attachment")
	if not attachment_url:
		return None, {"ok": False, "reason": "no_attachment"}
	pdf_path = _get_pdf_path_from_attachment(attachment_url)
	if not pdf_path:
		return None, {"ok": False, "reason": "pdf_not_found"}
	settings = _get_phamos_settings()
	if not settings:
		return None, {"ok": False, "reason": "mistral_not_configured"}
	pdf_b64 = _read_pdf_as_base64(pdf_path)
	ocr_base = (settings.get("base_url") or "").strip() or MISTRAL_OCR_BASE_URL
	if not ocr_base.endswith("/v1"):
		ocr_base = ocr_base.rstrip("/") + "/v1" if ocr_base else MISTRAL_OCR_BASE_URL
	try:
		markdown = _call_mistral_ocr(settings["api_key"], ocr_base, pdf_b64)
	except Exception as e:
		tb = frappe.get_traceback()
		frappe.log_error(title=_("Data extract from PDF failed"), message=tb)
		return None, {"ok": False, "reason": "error", "message": str(e)}
	if not (markdown or "").strip():
		return None, {"ok": False, "reason": "ocr_empty"}
	try:
		extracted = _call_mistral_chat_extract(
			settings["api_key"], settings["base_url"], settings["model"], markdown
		)
	except Exception as e:
		tb = frappe.get_traceback()
		frappe.log_error(title=_("Data extract from PDF failed"), message=tb)
		return None, {"ok": False, "reason": "error", "message": str(e)}
	return extracted, None


def _value_for_field_from_extracted(fieldname, extracted, key_map):
	"""Resolve value for one meta field from extracted dict (by fieldname or any key that maps to it)."""
	def norm(k):
		if not k or not isinstance(k, str):
			return None
		return cstr(k).strip().lower().replace(" ", "_").replace("-", "_")

	if not extracted:
		return None
	# Direct match by fieldname
	if fieldname in extracted and extracted[fieldname] not in (None, ""):
		return extracted[fieldname]
	# Any extracted key that maps to this fieldname (key_map has fieldname, label norm, aliases)
	for raw_key, value in extracted.items():
		if value is None or value == "":
			continue
		n = norm(raw_key)
		if key_map.get(n) == fieldname or key_map.get(raw_key) == fieldname:
			return value
	return None


def _build_review_fields(extracted):
	"""
	Build list of { fieldname, label, fieldtype, options, value } for dialog.
	Uses ALL extractable Accounting Receipt meta fields so nothing is missed;
	values are filled from extracted where we can match (by fieldname or key_map).
	"""
	key_map = get_extraction_key_map()
	meta_list = get_extractable_fields_meta()

	fields = []
	for meta in meta_list:
		fieldname = meta["fieldname"]
		value = _value_for_field_from_extracted(fieldname, extracted, key_map)
		fields.append({
			"fieldname": fieldname,
			"label": meta["label"],
			"fieldtype": meta["fieldtype"],
			"options": meta.get("options"),
			"value": value if value is None else str(value),
		})
	return fields


@frappe.whitelist()
def extract_from_pdf_for_review(accounting_receipt_name):
	"""
	Extract data from PDF and return it for user review (no update).
	Returns { ok, extracted, fields } where fields = [ { fieldname, label, fieldtype, value } ] for the dialog.
	"""
	extracted, err = _extract_from_pdf_only(accounting_receipt_name)
	if err:
		if err.get("reason") == "error":
			err["hint"] = _("Check Error Log for details")
		return err
	fields = _build_review_fields(extracted)
	return {"ok": True, "extracted": extracted, "fields": fields}


@frappe.whitelist()
def extract_from_pdf_now(accounting_receipt_name):
	"""
	Run PDF extraction synchronously and return result (for debugging / manual "Extract from PDF" button).
	Returns dict with ok, reason, updated, skipped, and on error: message or traceback.
	"""
	result = extract_from_pdf_and_update_ar(accounting_receipt_name)
	# If exception was logged, include link to Error Log
	if not result.get("ok") and result.get("reason") == "error":
		result["hint"] = _("Check Error Log for details")
	return result
