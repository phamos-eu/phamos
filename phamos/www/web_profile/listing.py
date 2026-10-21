# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Listing page for every Web Profile section (/en/people, /de/abteilungen, ...).

Reached only through the website_route_rules in hooks.py, which pass ``section`` and ``lang``.
Data: phamos.web_profile.sections (items) + phamos.web_profile.listing (filters, pages).
"""

from frappe import _
from frappe.utils import get_url

from phamos.web_profile.listing import build_listing
from phamos.web_profile.page import breadcrumb_schema, home_crumb, init_page, set_seo
from phamos.web_profile.sections import section_url


def get_context(context):
	section, lang = init_page(context)
	config = context.section_config
	listing = build_listing(section, lang)
	context.listing = listing
	context.section_title = _(config["title"])
	context.section_intro = _(config["intro"])
	context.search_placeholder = _(config["search_placeholder"])
	context.list_url = section_url(section, lang)
	context.crumbs = [home_crumb(), {"label": context.section_title, "url": context.list_url}]

	query = ""
	if listing["is_filtered"]:
		from frappe import request

		query = "?" + request.query_string.decode() if request and request.query_string else ""
	set_seo(
		context,
		title=f"{context.section_title} · phamos",
		description=context.section_intro,
		path=context.list_url + query,
		canonical_path=context.list_url,
		alternates={lng: section_url(section, lng) + query for lng in ("de", "en")},
		schema=[
			breadcrumb_schema(context.crumbs),
			{
				"@context": "https://schema.org",
				"@type": "CollectionPage",
				"name": context.section_title,
				"description": context.section_intro,
				"url": get_url(context.list_url),
				"inLanguage": lang,
			},
		],
	)
