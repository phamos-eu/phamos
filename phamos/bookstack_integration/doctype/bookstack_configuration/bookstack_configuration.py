# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BookstackConfiguration(Document):
	def validate(self):
		if self.instance_url:
			self.instance_url = self.instance_url.rstrip("/")

	@frappe.whitelist()
	def test_connection(self):
		from phamos.bookstack_integration.api_client import BookstackClient

		client = BookstackClient(self.name)
		# Cheap call: list a single user
		client.get("users", params={"count": 1})
		return _("Connection OK")

	@frappe.whitelist()
	def sync_all(self):
		from phamos.bookstack_integration import sync

		return sync.sync_instance(self.name)
