# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/dokumentation, /en/documentation: the published BookStack books as tiles, grouped by shelf
(phamos/phamos#2005, #2044)."""

from frappe import _

from phamos.web_profile import docs


def get_context(context):
	lang = docs.init_page(context)
	context.groups = docs.books_by_shelf(lang)
	context.intro = _("Guides for ERPNext and the Frappe Framework, written by our team.")
	docs.set_page_seo(context, title=_("Documentation"), description=context.intro, path_for=docs.docs_url)
