# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The one Mistral client of the app: OCR for PDFs and JSON chat completions.

Configuration lives in phamos Settings (Data Extract tab). Tests patch ocr_pdf and
chat_json, so nothing here talks to the network in tests.
"""

import base64
import json

import frappe
import requests

OCR_MODEL = "mistral-ocr-latest"
CHAT_MODEL_DEFAULT = "mistral-small-latest"
BASE_URL_DEFAULT = "https://api.mistral.ai/v1"
SETTINGS_DOCTYPE = "phamos Settings"


class LLMNotConfigured(frappe.ValidationError):
	pass


def get_mistral_settings():
	"""{"api_key", "model", "base_url"} from phamos Settings, or None when no API key is set."""
	try:
		settings = frappe.get_single(SETTINGS_DOCTYPE)
		api_key = settings.get_password("mistral_api_key") if settings.get("mistral_api_key") else None
	except Exception:
		return None
	if not api_key or not api_key.strip():
		return None
	return {
		"api_key": api_key.strip(),
		"model": (settings.get("mistral_model") or CHAT_MODEL_DEFAULT).strip(),
		"base_url": (settings.get("mistral_base_url") or "").strip() or BASE_URL_DEFAULT,
	}


def _require_settings():
	settings = get_mistral_settings()
	if not settings:
		raise LLMNotConfigured("Mistral is not configured: set the API key in phamos Settings > Data Extract.")
	return settings


def _api_base(settings):
	base = settings["base_url"].rstrip("/")
	return base if base.endswith("/v1") else base + "/v1"


def ocr_pdf(pdf_content):
	"""Markdown text of a PDF (all pages joined)."""
	settings = _require_settings()
	response = requests.post(
		f"{_api_base(settings)}/ocr",
		json={
			"model": OCR_MODEL,
			"document": {
				"type": "document_url",
				"document_url": "data:application/pdf;base64," + base64.b64encode(pdf_content).decode(),
			},
		},
		headers={"Authorization": f"Bearer {settings['api_key']}"},
		timeout=120,
	)
	if not response.ok:
		raise Exception(f"Mistral OCR failed ({response.status_code}): {response.text[:500]}")
	return "\n\n".join(page.get("markdown") or "" for page in response.json().get("pages") or [])


def chat_json(prompt, model=None, system=None):
	"""Ask a chat model for a JSON object and return it parsed."""
	settings = _require_settings()
	model = model or settings["model"]
	if "ocr" in model.lower():  # OCR models cannot chat
		model = CHAT_MODEL_DEFAULT
	messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
	response = requests.post(
		f"{_api_base(settings)}/chat/completions",
		json={"model": model, "messages": messages, "response_format": {"type": "json_object"}, "temperature": 0},
		headers={"Authorization": f"Bearer {settings['api_key']}"},
		timeout=90,
	)
	if not response.ok:
		raise Exception(f"Mistral chat failed ({response.status_code}): {response.text[:500]}")
	content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content") or "{}"
	return json.loads(content), model
