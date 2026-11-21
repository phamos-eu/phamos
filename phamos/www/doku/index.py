# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/doku: the published BookStack books as tiles, grouped by shelf (phamos/phamos#2005)."""

from frappe import _

from phamos.bookstack_integration.content import DOCS_ROUTE
from phamos.web_profile import docs


def get_context(context):
	docs.init_page(context)
	context.groups = docs.books_by_shelf()
	context.intro = _("Guides for ERPNext and the Frappe Framework, written by our team.")
	docs.set_page_seo(context, title=_("Documentation"), description=context.intro, path=DOCS_ROUTE)
