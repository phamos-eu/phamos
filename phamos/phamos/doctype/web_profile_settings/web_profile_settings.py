# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class WebProfileSettings(Document):
	"""Site-wide settings for the Web Profile pages, e.g. the fallback sales contact."""

	def validate(self):
		if self.sales_contact:
			party_type, published = frappe.db.get_value("Person Web Profile", self.sales_contact, ["party_type", "published"])
			if party_type != "Employee" or not published:
				frappe.throw(_("The sales contact must be a published Person Web Profile of a phamos employee."))
		# Social networks fetch og:image without a session: a private file would give them a 403 and no card.
		if self.share_image and self.share_image.startswith("/private/"):
			frappe.throw(_("The share image must be a public file. Upload it again without the \"Private\" option."))

	def on_update(self):
		frappe.cache.delete_value("web_profile_items")
