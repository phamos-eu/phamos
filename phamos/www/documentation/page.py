# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""/de/dokumentation/<book>/<page>: one documentation page with the book's contents beside it
(phamos/phamos#2005, #2044)."""

import frappe

from phamos.web_profile import docs


def get_context(context):
	lang = frappe.form_dict.get("lang")
	book = docs.find_book(frappe.form_dict.get("book_slug"), lang)
	page = book and docs.find_page(book, frappe.form_dict.get("page_slug"), lang)
	if not page:
		raise frappe.PageDoesNotExistError
	lang = docs.init_page(context, crumbs=[
		{"label": book.title, "url": book.url},
		{"label": page.title, "url": docs.page_url(book.slug, page.slug, lang)},
	])
	context.book = book
	context.page = page
	context.contents = docs.book_contents(book, lang)
	docs.set_page_seo(
		context,
		title=f"{page.title} · {book.title}",
		description=docs.describe(page.html, fallback=page.title),
		path_for=lambda lng: docs.page_url(book.slug, page.slug, lng),
	)
