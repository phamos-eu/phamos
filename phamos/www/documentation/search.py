# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/dokumentation/suche, /en/documentation/search: search in the published documentation
(phamos/phamos#2046). ?q=<words>, optionally &book=<slug> to search one book."""

import frappe
from frappe import _

from phamos.web_profile import docs, docs_search


def get_context(context):
	lang = docs.init_page(context, crumbs=[])
	query = (frappe.form_dict.get("q") or "").strip()[: docs_search.MAX_LENGTH]
	book = docs.find_book(frappe.form_dict.get("book"), lang) if frappe.form_dict.get("book") else None
	context.query = query
	context.book = book
	context.too_short = bool(query) and not docs_search.words_of(query)
	context.result = docs_search.search(query, lang, book_slug=book.slug if book else None)
	context.all_books_url = docs_search.search_url(lang, query) if book else None
	label = _("Search")
	context.crumbs.append({"label": label, "url": docs.search_path(lang)})
	docs.set_page_seo(context, title=_("Search the documentation"), description=_("Search the documentation"),
		path_for=docs.search_path)
	context.metatags["robots"] = "noindex, follow"  # result lists are not pages of their own
