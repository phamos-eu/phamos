# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class BookstackBook(Document):
	def on_update(self):
		# A new book has no earlier version; unpublished, it changes no links. (is_new() is already
		# False in on_update after an insert, so the earlier version is checked instead.)
		before = self.get_doc_before_save()
		was_published = before.publish_on_website if before else 0
		if bool(was_published) != bool(self.publish_on_website):
			self.refresh_website_copies()

	def refresh_website_copies(self):
		"""Make the next content sync pick up a changed "Publish on website" (#2004).

		An unpublished book's pages lose their copy at once. Pages of the other published
		books are fetched again, because their links to this book change: they point to
		phamos.eu while it is published, and back to BookStack once it is not.
		"""
		page = frappe.qb.DocType("Bookstack Page")
		if not self.publish_on_website:
			(
				frappe.qb.update(page)
				.set(page.html, None)
				.set(page.content_updated_at, None)
				.where(page.book == self.name)
			).run()

		others = frappe.get_all(
			"Bookstack Book",
			filters={"instance": self.instance, "publish_on_website": 1, "name": ["!=", self.name]},
			pluck="name",
		)
		if others:
			(
				frappe.qb.update(page)
				.set(page.content_updated_at, None)
				.where(page.book.isin(others))
			).run()
