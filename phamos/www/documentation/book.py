# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/dokumentation/<book>: summary and table of contents of one published book (phamos/phamos#2005, #2044)."""

import frappe
from frappe import _

from phamos.web_profile import docs
from phamos.web_profile.sections import modules_for_book


def get_context(context):
	lang = frappe.form_dict.get("lang")
	book = docs.find_book(frappe.form_dict.get("book_slug"), lang)
	if not book:
		raise frappe.PageDoesNotExistError
	lang = docs.init_page(context, crumbs=[{"label": book.title, "url": book.url}])
	context.book = book
	context.contents = docs.book_contents(book, lang)
	context.modules = modules_for_book(book.name, lang)  # module pages that link this book (#2006)
	docs.set_page_seo(
		context,
		title=f"{book.title} · {_('Documentation')}",
		description=docs.describe(book.summary, fallback=book.title),
		path_for=lambda lng: docs.book_url(book.slug, lng),
	)
