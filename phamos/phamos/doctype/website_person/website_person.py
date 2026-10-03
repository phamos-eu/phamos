# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.website.website_generator import WebsiteGenerator


class WebsitePerson(WebsiteGenerator):
	def before_save(self):
		if not self.sort_order:
			self.sort_order = frappe.db.count(self.doctype) + 1

	def get_context(self, context):
		context.parents = [{"title": "People", "route": "/people"}]
