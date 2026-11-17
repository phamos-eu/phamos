import re
import time

import frappe
import requests

from phamos.phamos.doctype.accounting_receipt.mistral_pdf import _get_phamos_settings

MISTRAL_IMAGE_MODEL = "mistral-medium-latest"
_IMAGE_URL_RE = re.compile(r"https?://[^\s\)\]>\"']+")


def format_author_note(text):
	"""Keep 3 or 4 plain lines, as separate paragraphs under the image."""
	lines = []
	for line in (text or "").replace("\r", "").split("\n"):
		line = line.strip().lstrip("-•*").strip()
		if line:
			lines.append(line)
	return "\n\n".join(lines[:4])


def author_note(quote):
	"""Three or four lines about the quote's author. Empty string if that cannot be written."""
	_quote_text, author = parse_quote(quote)
	if not author or author.lower() == "unknown":
		return ""

	settings = _get_phamos_settings()
	if not settings:
		return ""

	try:
		resp = requests.post(
			f"{_v1(settings['base_url'])}/chat/completions",
			json={
				"model": "mistral-small-latest",
				"temperature": 0.4,
				"messages": [
					{
						"role": "system",
						"content": (
							"Write a short note about a real person for a team morning message. "
							"Use 3 or 4 lines. One plain sentence per line. "
							"No title, no bullets, no hashtags, no quotation marks."
						),
					},
					{
						"role": "user",
						"content": (
							f"Who is {author}? Write 3 or 4 lines about who they are "
							"and why they are remembered."
						),
					},
				],
			},
			headers=_mistral_headers(settings["api_key"]),
			timeout=60,
		)
		if not resp.ok:
			body = resp.text[:300] if resp.text else ""
			raise Exception(f"Mistral author note failed ({resp.status_code}): {body}")

		message = ((resp.json().get("choices") or [{}])[0].get("message") or {})
		content = message.get("content") or ""
		if isinstance(content, list):
			content = "\n".join(
				chunk.get("text", "")
				for chunk in content
				if isinstance(chunk, dict)
			)
		return format_author_note(content)
	except Exception:
		frappe.log_error(
			title="Raven Daily Thread: author note failed",
			message=frappe.get_traceback(),
		)
		return ""


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


def build_quote_poster_prompt(quote_text, author):
	"""Used when a real-person portrait is refused. Still must return an image."""
	return f"""Create a vertical inspirational quote poster. Do not depict a real person or a recognizable portrait.

Soft ink-wash / watercolor illustration, muted earth tones, serene morning light (misty mountains, bamboo, a quiet library, or an open book).

Include clearly readable text:
"{quote_text}"
— {author}

Warm, uplifting, suitable for a team good-morning message. Portrait orientation. No logos and no watermarks.
"""


def _mistral_headers(api_key):
	return {
		"Authorization": f"Bearer {api_key}",
		"Content-Type": "application/json",
		"Accept": "application/json",
	}


def _v1(base_url):
	base = (base_url or "https://api.mistral.ai/v1").strip().rstrip("/")
	if not base.endswith("/v1"):
		base += "/v1"
	return base


def _content_chunks(content):
	if isinstance(content, dict):
		return [content]
	if isinstance(content, list):
		return [chunk for chunk in content if isinstance(chunk, dict)]
	return []


def _iter_content_pieces(data):
	"""Yield text strings and content chunks from conversation or chat-completion payloads."""
	if not isinstance(data, dict):
		return

	containers = []
	outputs = data.get("outputs") or data.get("entries") or []
	if isinstance(outputs, dict):
		outputs = [outputs]
	if isinstance(outputs, list):
		containers.extend(outputs)

	for choice in data.get("choices") or []:
		if not isinstance(choice, dict):
			continue
		messages = list(choice.get("messages") or [])
		if isinstance(choice.get("message"), dict):
			messages.append(choice["message"])
		containers.extend(messages)

	for item in containers:
		if not isinstance(item, dict):
			continue
		content = item.get("content")
		if isinstance(content, str):
			yield content
		else:
			yield from _content_chunks(content)
		if item.get("file_id"):
			yield item


def _image_url_from_chunk(chunk):
	url = chunk.get("image_url") or chunk.get("url")
	if isinstance(url, dict):
		url = url.get("url")
	if isinstance(url, str) and url.startswith("http"):
		return url
	return None


def _looks_like_image_url(url):
	lower = url.lower()
	path = lower.split("?", 1)[0]
	return "files.mistral.ai" in lower or path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def _ext_from_url(url):
	path = (url or "").split("?", 1)[0].lower()
	for ext in ("png", "jpg", "jpeg", "webp", "gif"):
		if path.endswith("." + ext):
			return "jpg" if ext == "jpeg" else ext
	return "png"


def _extract_image(data):
	"""Return (file_id, file_type, image_url) from a Mistral image response."""
	pieces = list(_iter_content_pieces(data))
	dicts = [piece for piece in pieces if isinstance(piece, dict)]

	for chunk in reversed(dicts):
		if chunk.get("type") == "tool_file" and chunk.get("file_id"):
			return chunk.get("file_id"), chunk.get("file_type") or "png", None
	for chunk in reversed(dicts):
		if chunk.get("file_id"):
			return chunk.get("file_id"), chunk.get("file_type") or "png", None
	for chunk in reversed(dicts):
		url = _image_url_from_chunk(chunk)
		if url:
			return None, _ext_from_url(url), url
	for piece in pieces:
		if not isinstance(piece, str):
			continue
		for url in _IMAGE_URL_RE.findall(piece):
			if _looks_like_image_url(url):
				return None, _ext_from_url(url), url
	return None, None, None


def _extract_file_id_from_conversation(data):
	file_id, file_type, _url = _extract_image(data)
	return file_id, file_type


def _conversation_hint(data):
	texts = []
	for piece in _iter_content_pieces(data):
		if isinstance(piece, str) and piece.strip():
			texts.append(piece.strip())
		elif isinstance(piece, dict):
			text = piece.get("text")
			if isinstance(text, str) and text.strip():
				texts.append(text.strip())
	hint = " ".join(texts)[:300]
	return hint or "Response had no image file."


def _post_image_completion(api_key, base_url, prompt):
	"""Built-in image_generation tool on chat completions. Agents often reply with text only."""
	resp = requests.post(
		f"{_v1(base_url)}/chat/completions",
		json={
			"model": MISTRAL_IMAGE_MODEL,
			"messages": [
				{
					"role": "system",
					"content": "Call the image_generation tool. Do not answer with text only.",
				},
				{"role": "user", "content": prompt},
			],
			"tools": [{"type": "image_generation"}],
		},
		headers=_mistral_headers(api_key),
		timeout=240,
	)
	if not resp.ok:
		body = resp.text[:500] if resp.text else ""
		raise Exception(f"Mistral image completion failed ({resp.status_code}): {body}")
	return resp.json()


def _download_mistral_file(base_url, api_key, file_id, retries=5, delay=2):
	download_url = f"{_v1(base_url)}/files/{file_id}/content"
	headers = {
		"Authorization": f"Bearer {api_key}",
		"Accept": "application/octet-stream",
	}

	for attempt in range(retries):
		file_resp = requests.get(download_url, headers=headers, timeout=120)
		if file_resp.ok:
			return file_resp
		if file_resp.status_code != 404 or attempt == retries - 1:
			body = file_resp.text[:500] if file_resp.text else ""
			raise Exception(
				f"Mistral image download failed ({file_resp.status_code}): {body}"
			)
		time.sleep(delay * (attempt + 1))


def _download_image_url(url, api_key):
	headers = {"Authorization": f"Bearer {api_key}", "Accept": "image/*,*/*"}
	file_resp = requests.get(url, headers=headers, timeout=120)
	if not file_resp.ok:
		file_resp = requests.get(url, timeout=120)
	if not file_resp.ok:
		body = file_resp.text[:300] if file_resp.text else ""
		raise Exception(f"Mistral image download failed ({file_resp.status_code}): {body}")
	return file_resp


def generate_daily_image_from_quote(quote):
	"""Generate an image via Mistral's image_generation tool and return a File URL."""
	settings = _get_phamos_settings()
	if not settings:
		frappe.throw(
			"Mistral API key is not configured. Add it under phamos Settings > Data Extract."
		)

	api_key = settings["api_key"]
	base_url = settings["base_url"]
	quote_text, author = parse_quote(quote)
	prompts = [
		build_author_portrait_prompt(quote_text, author),
		build_quote_poster_prompt(quote_text, author),
	]

	last_data = None
	file_id = file_type = image_url = None
	for prompt in prompts:
		last_data = _post_image_completion(api_key, base_url, prompt)
		file_id, file_type, image_url = _extract_image(last_data)
		if file_id or image_url:
			break

	if not file_id and not image_url:
		raise Exception(
			"Mistral did not return a generated image file. " + _conversation_hint(last_data)
		)

	if file_id:
		file_resp = _download_mistral_file(base_url, api_key, file_id)
	else:
		file_resp = _download_image_url(image_url, api_key)
		file_type = _ext_from_url(image_url)

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
