# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from phamos.web_profile.docs import clear_cache as clear_docs_cache


class BookstackBook(Document):
	def validate(self):
		self.validate_unique_web_address()

	def validate_unique_web_address(self):
		"""Two published books with one slug would share /de/doku/<slug>; only one could be shown,
		and links of the other instance would lead to the wrong book (review S9)."""
		# Only when someone publishes: the sync saves published books too, and a slug BookStack renamed
		# into a clash must not make every sync fail (the website shows one of the two anyway).
		if not (self.publish_on_website and self.slug and self.has_value_changed("publish_on_website")):
			return
		if frappe.db.exists("Bookstack Book", {"publish_on_website": 1, "slug": self.slug, "name": ["!=", self.name]}):
			frappe.throw(frappe._("Another published book already uses the web address /de/doku/{0}.").format(self.slug))

	def on_update(self):
		# A new book has no earlier version; unpublished, it changes no links. (is_new() is already
		# False in on_update after an insert, so the earlier version is checked instead.)
		before = self.get_doc_before_save()
		was_published = before.publish_on_website if before else 0
		if bool(was_published) != bool(self.publish_on_website):
			self.refresh_website_copies()
		# After the commit: a request between clearing and committing would cache the old rows again.
		frappe.db.after_commit.add(clear_docs_cache)

	def on_trash(self):
		# The sync deletes with force=True, which skips link checks: module profiles would keep a row
		# pointing to the missing book and fail on their next save (review S4, #2006).
		frappe.db.delete("Web Profile Book", {"book": self.name})
		frappe.db.after_commit.add(lambda: frappe.cache.delete_value("web_profile_items"))
		frappe.db.after_commit.add(clear_docs_cache)

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
