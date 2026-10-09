"""Context shared by the listing and profile www pages: language, SEO tags, hreflang, breadcrumbs."""

import json

import frappe
from frappe import _
from frappe.utils import get_url

from phamos.web_profile.i18n import DEFAULT_LANGUAGE, LANGUAGES, set_request_language
from phamos.web_profile.sections import SECTIONS

LANGUAGE_NAMES = {"de": "Deutsch", "en": "English"}


def init_page(context):
	"""Validate the route defaults set by website_route_rules and switch the request language."""
	section = frappe.form_dict.get("section")
	if section not in SECTIONS:
		# The www files are only reachable through the localized route rules.
		raise frappe.PageDoesNotExistError
	lang = set_request_language(frappe.form_dict.get("lang"), context)
	context.no_cache = 1
	context.no_breadcrumbs = 1
	context.lang = lang
	context.section = section
	context.section_config = SECTIONS[section]
	return section, lang


def set_seo(context, *, title, description, path, alternates, image=None, canonical_path=None, schema=None):
	"""Title, description, canonical, hreflang (+ x-default), Open Graph / Twitter and JSON-LD."""
	context.title = title
	context.page_title = title
	context.canonical_url = get_url(canonical_path or path)
	context.alternate_links = [{"lang": lang, "url": get_url(url)} for lang, url in alternates.items()]
	context.alternate_links.append({"lang": "x-default", "url": get_url(alternates[DEFAULT_LANGUAGE])})
	context.language_links = [
		{"lang": lang, "label": LANGUAGE_NAMES[lang], "url": alternates[lang], "current": lang == context.lang}
		for lang in LANGUAGES
	]
	context.metatags = {
		"title": title,
		"description": description,
		"url": context.canonical_url,
		"image": image or None,
		"og:type": "website",
		"og:locale": "de_DE" if context.lang == "de" else "en_US",
	}
	context.description = description
	# Rendered raw inside <script type="application/ld+json">; "</" is escaped so data can't close the tag.
	context.jsonld = json.dumps([s for s in schema or [] if s], ensure_ascii=False).replace("</", "<\\/")


def breadcrumb_schema(crumbs):
	return {
		"@context": "https://schema.org",
		"@type": "BreadcrumbList",
		"itemListElement": [
			{"@type": "ListItem", "position": i + 1, "name": c["label"], "item": get_url(c["url"])}
			for i, c in enumerate(crumbs)
		],
	}


def home_crumb():
	return {"label": _("Home"), "url": "/"}
