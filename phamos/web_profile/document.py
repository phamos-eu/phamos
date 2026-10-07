"""Base controller shared by every ``<Source> Web Profile`` doctype."""

import frappe
from frappe.model.document import Document

from phamos.web_profile.mirror import refresh_mirrored_fields
from phamos.web_profile.utils import slugify

# Field used to build the default route slug per profile doctype.
TITLE_FIELDS = {
	"Person Web Profile": "full_name",
	"Department Web Profile": "department_name",
	"Team Web Profile": "team_name",
	"Module Web Profile": "module_name",
	"Implementation Web Profile": "title_en",
	"Industry Web Profile": "industry",
	"Stakeholder Web Profile": "party_name",
}


class WebProfileDocument(Document):
	def validate(self):
		refresh_mirrored_fields(self)
		self.set_route()

	def on_update(self):
		# Listings and profiles are rendered from cached item lists (see sections.py).
		frappe.cache.delete_value("web_profile_items")

	def on_trash(self):
		frappe.cache.delete_value("web_profile_items")

	def set_route(self):
		"""Generate a stable, lowercase, hyphenated slug once; editors may override it."""
		if self.route:
			self.route = slugify(self.route)
		else:
			base = slugify(self.get(TITLE_FIELDS[self.doctype]) or self.name)
			self.route = base
			counter = 2
			while frappe.db.exists(self.doctype, {"route": self.route, "name": ["!=", self.name]}):
				self.route = f"{base}-{counter}"
				counter += 1
