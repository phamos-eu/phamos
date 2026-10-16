"""Where the newsletter confirmation link ends (Email Group "welcome_url"): says plainly that the address
is confirmed, what follows, how to unsubscribe, and leads back to the event. Frappe has no page of its
own for this (it either redirects here or shows a bare "Confirmed" message)."""

from urllib.parse import quote

import frappe
from frappe import _

from phamos.hooks import SUBSCRIPTION_CONFIRMED_ROUTES
from phamos.web_profile.page import init_page, set_seo
from phamos.web_profile.sections import find_item, section_url

no_cache = 1


def get_context(context):
	_section, lang = init_page(context)
	slug = (frappe.form_dict.get("event") or "").strip()[:140]
	item = find_item("events", slug, lang) if slug else None
	context.item = item
	context.events_url = section_url("events", lang)
	title = _("Subscription confirmed")
	query = f"?event={quote(slug)}" if item else ""
	set_seo(context, title=title, description=title, path=f"/{SUBSCRIPTION_CONFIRMED_ROUTES[lang]}{query}",
		alternates={code: f"/{route}{query}" for code, route in SUBSCRIPTION_CONFIRMED_ROUTES.items()})
	context.metatags["robots"] = "noindex"
	return context
