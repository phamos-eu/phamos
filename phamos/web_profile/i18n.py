"""Language handling for the Web Profile pages: /de and /en path prefixes with localized slugs.

The language comes from the route (``lang`` default in website_route_rules), never from the
visitor's cookie, so every URL has exactly one language for search engines (hreflang pairs).
"""

import frappe

LANGUAGES = ("de", "en")
DEFAULT_LANGUAGE = "de"  # x-default; old and unprefixed URLs are redirected to /de/... (phamos/phamos#1492)


def set_request_language(lang, context):
	"""Switch translation for the rest of the request and fix the <html lang> boot value."""
	lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
	frappe.local.lang = lang
	if context.get("boot"):
		context.boot["lang"] = lang
	return lang


def localized(record, field, lang, fallback=True):
	"""``field`` (title, summary, content) of the record's text row in ``lang``.

	``record.texts`` is {language: row} from the "Web Profile Content" table (see
	sections.attach_texts). A missing value falls back to German, then to any other language,
	unless ``fallback`` is off (e.g. names that have a better non-text fallback).
	"""
	texts = record.get("texts") or {}
	languages = [lang, *([DEFAULT_LANGUAGE, *texts] if fallback else [])]
	for code in languages:
		value = (texts.get(code) or {}).get(field)
		if value:
			return value
	return ""
