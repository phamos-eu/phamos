# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/doku/<book>: summary and table of contents of one published book (phamos/phamos#2005)."""

import frappe
from frappe import _

from phamos.web_profile import docs
from phamos.web_profile.sections import modules_for_book


def get_context(context):
	book = docs.find_book(frappe.form_dict.get("book_slug"))
	if not book:
		raise frappe.PageDoesNotExistError
	docs.init_page(context, crumbs=[{"label": book.title, "url": book.url}])
	context.book = book
	context.contents = docs.book_contents(book)
	first = docs.reading_order(context.contents)
	context.first_page = first[0] if first else None
	context.modules = modules_for_book(book.name, "de")  # module pages that link this book (#2006)
	docs.set_page_seo(
		context,
		title=f"{book.title} · {_('Documentation')}",
		description=docs.describe(book.summary, fallback=book.title),
		path=book.url,
	)
