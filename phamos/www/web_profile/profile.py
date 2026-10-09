# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Profile page for one Web Profile record (/en/people/<slug>, /de/abteilungen/<slug>, ...).

Same skeleton for every section: breadcrumb, header, facts strip, answer-first summary + body,
related tile sections and one call to action. What fills it comes from sections.build_profile.
Every record has one neutral URL from its creation, also when it is shown anonymously
(phamos/phamos#1512); an unpublished record is not found.
"""

import frappe
from frappe import _
from frappe.utils import get_url, strip_html

from phamos.web_profile.page import breadcrumb_schema, home_crumb, init_page, set_seo
from phamos.web_profile.sections import build_profile, find_item, item_url, section_url


def get_context(context):
	section, lang = init_page(context)
	slug = frappe.form_dict.get("slug")
	item = find_item(section, slug, lang)
	if not item:
		raise frappe.PageDoesNotExistError

	profile = build_profile(item, lang)
	context.item = item
	context.profile = profile
	context.section_title = _(context.section_config["title"])
	context.list_url = section_url(section, lang)
	context.crumbs = [home_crumb(), {"label": context.section_title, "url": context.list_url},
		{"label": item.title, "url": item.url}]

	description = strip_html(item.summary or item.subtitle or context.section_config["intro"])[:160]
	schema = profile["schema"]
	if schema:
		schema = {"@context": "https://schema.org", **schema, "url": get_url(item.url), "inLanguage": lang}
		if item.image:
			schema["image"] = get_url(item.image)
	set_seo(
		context,
		title=f"{item.title} · {context.section_title} · phamos",
		description=description,
		path=item.url,
		image=get_url(item.image) if item.image else None,
		alternates={lng: item_url(section, item.slug, lng) for lng in ("de", "en")},
		schema=[breadcrumb_schema(context.crumbs), schema],
	)
	if item.masked and section == "people":
		# Anonymous people are not indexed (re-identification risk, no search value). Anonymous
		# customers and case studies stay indexable: their topic is what prospects search for.
		context.metatags["robots"] = "noindex"
