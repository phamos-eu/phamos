"""Base controller shared by every ``<Source> Web Profile`` doctype."""

import frappe
from frappe import _
from frappe.model.document import Document

from phamos.web_profile.mirror import refresh_mirrored_fields
from phamos.web_profile.utils import slugify

# Field used to build the default route slug per profile doctype.
TITLE_FIELDS = {
	"Person Web Profile": "full_name",
	"Department Web Profile": "department_name",
	"Team Web Profile": "team_name",
	"Module Web Profile": "module_name",
	"Implementation Web Profile": None,  # the public case title of a text row, see route_title
	"Industry Web Profile": "industry",
	"Stakeholder Web Profile": "party_name",
}


class WebProfileDocument(Document):
	def validate(self):
		refresh_mirrored_fields(self)
		self.validate_translations()
		self.set_route()

	def validate_translations(self):
		"""One "Web Profile Content" row per language."""
		seen = set()
		for row in self.get("translations") or []:
			if row.language in seen:
				frappe.throw(_("Row {0}: there is already a text row for language {1}.").format(row.idx, row.language))
			seen.add(row.language)

	def route_title(self):
		"""Text the default slug is built from: the title field, or the case title of a text row."""
		field = TITLE_FIELDS[self.doctype]
		if field:
			return self.get(field)
		rows = sorted(self.get("translations") or [], key=lambda r: r.language != "de")  # German first
		return next((r.title for r in rows if r.title), None)

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
			base = slugify(self.route_title() or self.name)
			self.route = base
			counter = 2
			while frappe.db.exists(self.doctype, {"route": self.route, "name": ["!=", self.name]}):
				self.route = f"{base}-{counter}"
				counter += 1
