"""Navbar, footer and language handling for every website page (phamos/phamos#1502).

- Every page gets a language: Web Profile pages from their route, Web Pages from their
  "Language" field, all other pages (blog, help articles, login, …) keep Frappe's choice.
- Navbar and footer links are kept in Website Settings with German URLs (/de/…); on an English
  page every link to a Web Profile section or to a translated Web Page is swapped for its English
  counterpart (and the other way round).
- The footer groups "Modules" and "Industries" are filled with the published Module / Industry
  Web Profiles (kept as empty headings in Website Settings).
- The footer's bottom area shows the company data like a DIN 5008 letter footer, taken from the
  ERPNext Company, its Address and its default Bank Account (IBAN masked).
"""

import frappe
from frappe import _
from frappe.model.base_document import BaseDocument
from frappe.utils import get_url

from phamos.web_profile.i18n import DEFAULT_LANGUAGE, LANGUAGES

# Footer headings (English source label or the German label already in Website Settings) that are
# generated from a Web Profile section.
GENERATED_GROUPS = {"Modules": "modules", "Module": "modules", "Industries": "industries", "Branchen": "industries"}


def update_website_context(context):
	lang = _page_language(context)
	if lang:
		frappe.local.lang = lang
		if context.get("boot"):
			context.boot["lang"] = lang
	lang = lang or (frappe.local.lang if frappe.local.lang in LANGUAGES else DEFAULT_LANGUAGE)

	values = {
		"top_bar_items": [_translate_item(item, lang) for item in context.get("top_bar_items") or []],
		"footer_items": _footer_items(context.get("footer_items") or [], lang),
		"wp_company_footer": company_footer(),
		"wp_lang": lang,
	}
	if context.get("doc") and getattr(context.doc, "doctype", None) == "Web Page" and context.doc.get("language"):
		values["head_include"] = (context.get("head_include") or "") + _web_page_alternates(context.doc)
	return values


# --- language --------------------------------------------------------------------------------------


def _page_language(context):
	if context.get("section_config") and context.get("lang") in LANGUAGES:  # Web Profile pages
		return context.lang
	doc = context.get("doc")
	if doc is not None and getattr(doc, "doctype", None) == "Web Page" and doc.get("language") in LANGUAGES:
		return doc.language
	return None


def _translation_group(page):
	"""{lang: route} of a Web Page and all its translations."""
	master = page.get("translation_of") or page.get("name")
	rows = frappe.get_all("Web Page", filters={"published": 1}, or_filters={"name": master, "translation_of": master},
		fields=["route", "language"])
	return {r.language: r.route for r in rows if r.language}


def _web_page_alternates(page):
	group = _translation_group(page)
	if len(group) < 2:
		return ""
	links = [f'<link rel="alternate" hreflang="{lang}" href="{get_url("/" + route)}">' for lang, route in group.items()]
	if DEFAULT_LANGUAGE in group:
		links.append(f'<link rel="alternate" hreflang="x-default" href="{get_url("/" + group[DEFAULT_LANGUAGE])}">')
	links.append(f'<link rel="canonical" href="{get_url("/" + page.route)}">')
	return "\n".join(links)


def translate_url(url, lang):
	"""'/de/personen/x' -> '/en/people/x', '/de/preise' -> '/en/pricing'; other URLs unchanged."""
	if not url or not url.startswith("/"):
		return url
	parts = url.strip("/").split("/")
	if len(parts) < 2 or parts[0] not in LANGUAGES or parts[0] == lang:
		return url
	from phamos.web_profile.sections import SECTIONS

	for config in SECTIONS.values():
		if config["slugs"].get(parts[0]) == parts[1]:
			return "/" + "/".join([lang, config["slugs"][lang], *parts[2:]])
	page = frappe.db.get_value("Web Page", {"route": url.strip("/"), "published": 1},
		["name", "translation_of"], as_dict=True)
	if page:
		target = _translation_group(page).get(lang)
		if target:
			return "/" + target
	return url


# --- navbar and footer ------------------------------------------------------------------------------


def _translate_item(item, lang):
	"""Copy (never mutate the cached Website Settings rows) with the URL in the page language."""
	children = item.get("child_items")
	# Website Settings passes Top Bar Item documents, frappe.website...get_items plain dicts
	copy = frappe._dict(item.as_dict() if isinstance(item, BaseDocument) else item)
	copy.url = translate_url(copy.get("url"), lang)
	copy.label = _(copy.get("label"))  # Frappe's footer template prints labels untranslated
	if children:
		copy.child_items = [_translate_item(child, lang) for child in children]
	return copy


def _footer_items(items, lang):
	from phamos.web_profile.sections import get_items

	out = []
	for item in items:
		copy = _translate_item(item, lang)
		label, parent = (item.get("label"), item.get("parent_label"))
		section = GENERATED_GROUPS.get(label)
		if section and not parent:
			profiles = sorted(get_items(section, lang), key=lambda i: i.sort["manual"])
			copy.child_items = [frappe._dict(label=p.title, url=p.url, parent_label=label) for p in profiles]
		out.append(copy)
	return out


# --- DIN 5008 footer --------------------------------------------------------------------------------


def company_footer():
	"""Four columns like a DIN 5008 letter footer, from the default Company (cached per request)."""
	cached = getattr(frappe.local, "wp_company_footer", None)
	if cached is not None:
		return cached
	company = frappe.defaults.get_global_default("company") or (frappe.get_all("Company", pluck="name", limit=1) or [None])[0]
	footer = frappe._dict()
	if company:
		c = frappe.db.get_value("Company", company,
			["company_name", "phone_no", "email", "website", "tax_id", "registration_details"], as_dict=True)
		address = _company_address(company)
		bank = _company_bank(company)
		footer = frappe._dict(
			name=c.company_name,
			address_lines=address,
			phone=c.phone_no,
			email=c.email,
			website=c.website,
			register_lines=[line.strip() for line in (c.registration_details or "").splitlines() if line.strip()],
			tax_id=c.tax_id,
			bank=bank,
		)
	frappe.local.wp_company_footer = footer
	return footer


def _company_address(company):
	links = frappe.get_all("Dynamic Link", filters={"parenttype": "Address", "link_doctype": "Company", "link_name": company},
		pluck="parent")
	if not links:
		return []
	rows = frappe.get_all("Address", filters={"name": ["in", links], "disabled": 0},
		fields=["address_line1", "address_line2", "pincode", "city", "country", "is_primary_address"],
		order_by="is_primary_address desc, creation asc", limit=1)
	if not rows:
		return []
	a = rows[0]
	return [line for line in [a.address_line1, a.address_line2, " ".join(filter(None, [a.pincode, a.city])),
		_(a.country) if a.country else None] if line]


def _company_bank(company):
	rows = frappe.get_all("Bank Account", filters={"company": company, "is_company_account": 1, "disabled": 0},
		fields=["bank", "iban"], order_by="is_default desc, creation asc", limit=1)
	if not rows or not rows[0].iban:
		return None
	bic = frappe.db.get_value("Bank", rows[0].bank, "swift_number") if rows[0].bank else None
	return frappe._dict(name=rows[0].bank, iban=mask_iban(rows[0].iban), bic=bic)


def mask_iban(iban):
	"""'DE37120300001077032371' -> 'DE37 **** **** **** **23 71': country, check digits and last 4."""
	compact = "".join((iban or "").split()).upper()
	if len(compact) < 10:
		return compact
	masked = compact[:4] + "*" * (len(compact) - 8) + compact[-4:]
	return " ".join(masked[i : i + 4] for i in range(0, len(masked), 4))
