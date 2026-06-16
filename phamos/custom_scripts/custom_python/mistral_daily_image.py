import frappe
import requests

from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings

MISTRAL_IMAGE_AGENT_CACHE_KEY = "phamos_mistral_image_agent_id_v2"
MISTRAL_IMAGE_AGENT_MODEL = "mistral-medium-latest"


def parse_quote(quote):
	"""Split 'Quote text - Author Name' into quote and author."""
	quote = (quote or "").strip()
	if " - " in quote:
		text, author = quote.rsplit(" - ", 1)
		return text.strip().strip('"'), author.strip()
	return quote.strip().strip('"'), "Unknown"


def build_author_portrait_prompt(quote_text, author):
	return f"""Create a vertical inspirational wisdom poster in the style of a traditional ink-wash / watercolor illustration (soft brush strokes, muted earth tones, serene atmosphere).

Central figure: a dignified, respectful portrait of {author}, shown as the author of the quote — wise, calm, and thoughtful. Dress and setting should fit {author}'s era and culture (e.g. writer's study, books, pipe, or peaceful landscape for Western authors; scholar robes and bamboo for Eastern philosophers). Artistic illustration only, not a photo.

Include clearly readable text on the image in elegant classic typography (serif or calligraphic):
"{quote_text}"
— {author}

Layout like a classic quote poster: quote text in the upper area, author figure seated or standing below, peaceful background (misty mountains, bamboo, soft morning light, or a quiet library). Warm, uplifting, suitable for a team good-morning message. Portrait orientation.
"""


def _mistral_headers(api_key):
	return {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _get_or_create_image_agent(api_key, base_url):
	agent_id = frappe.cache.get_value(MISTRAL_IMAGE_AGENT_CACHE_KEY)
	if agent_id:
		return agent_id

	url = f"{base_url.rstrip('/')}/agents"
	payload = {
		"model": MISTRAL_IMAGE_AGENT_MODEL,
		"name": "Phamos Daily Image Agent",
		"description": "Generates motivational images for the daily Raven thread.",
		"instructions": (
			"Use the image_generation tool to create inspirational quote posters. "
			"Each image must show a respectful portrait of the quoted author and include "
			"the quote text and author name as readable typography on the image."
		),
		"tools": [{"type": "image_generation"}],
		"completion_args": {"temperature": 0.3, "top_p": 0.95},
	}
	resp = requests.post(url, json=payload, headers=_mistral_headers(api_key), timeout=60)
	if not resp.ok:
		body = resp.text[:500] if resp.text else ""
		raise Exception(f"Mistral agent creation failed ({resp.status_code}): {body}")

	agent_id = resp.json().get("id")
	if not agent_id:
		raise Exception("Mistral agent creation did not return an agent id.")

	frappe.cache.set_value(MISTRAL_IMAGE_AGENT_CACHE_KEY, agent_id)
	return agent_id


def _extract_file_id_from_conversation(data):
	for output in data.get("outputs") or []:
		content = output.get("content")
		if not isinstance(content, list):
			continue
		for chunk in content:
			if (
				isinstance(chunk, dict)
				and chunk.get("type") == "tool_file"
				and chunk.get("file_id")
			):
				return chunk.get("file_id"), chunk.get("file_type") or "png"
	return None, None


def generate_daily_image_from_quote(quote):
	"""Generate an image via Mistral Agents image_generation tool and return a File URL."""
	settings = _get_phamos_settings()
	if not settings:
		frappe.throw(
			"Mistral API key is not configured. Add it under phamos Settings > Data Extract."
		)

	api_key = settings["api_key"]
	base_url = settings["base_url"]
	agent_id = _get_or_create_image_agent(api_key, base_url)

	quote_text, author = parse_quote(quote)
	prompt = build_author_portrait_prompt(quote_text, author)

	conv_url = f"{base_url.rstrip('/')}/conversations"
	conv_resp = requests.post(
		conv_url,
		json={"agent_id": agent_id, "inputs": prompt, "stream": False},
		headers=_mistral_headers(api_key),
		timeout=180,
	)
	if not conv_resp.ok:
		body = conv_resp.text[:500] if conv_resp.text else ""
		raise Exception(f"Mistral image conversation failed ({conv_resp.status_code}): {body}")

	file_id, file_type = _extract_file_id_from_conversation(conv_resp.json())
	if not file_id:
		raise Exception("Mistral did not return a generated image file.")

	download_url = f"{base_url.rstrip('/')}/files/{file_id}/content"
	file_resp = requests.get(
		download_url,
		headers={
			"Authorization": f"Bearer {api_key}",
			"Accept": "application/octet-stream",
		},
		timeout=120,
	)
	if not file_resp.ok:
		body = file_resp.text[:500] if file_resp.text else ""
		raise Exception(f"Mistral image download failed ({file_resp.status_code}): {body}")

	ext = (file_type or "png").lower()
	if ext == "jpeg":
		ext = "jpg"
	if ext not in ("png", "jpg", "webp", "gif"):
		ext = "png"

	today = frappe.utils.today()
	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"daily-motivation-{today}.{ext}",
			"content": file_resp.content,
			"is_private": 0,
		}
	).insert(ignore_permissions=True)
	return file_doc.file_url
