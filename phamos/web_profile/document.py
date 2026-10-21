"""Base controller shared by every ``<Source> Web Profile`` doctype."""

import frappe
from frappe import _
from frappe.model.document import Document

from phamos.web_profile.mirror import refresh_mirrored_fields
from phamos.web_profile.utils import slugify

# Field used to build the default route slug. Person, Stakeholder and Implementation Web Profiles
# build neutral routes in their own set_route (phamos/phamos#1512).
TITLE_FIELDS = {
	"Department Web Profile": "department_name",
	"Team Web Profile": "team_name",
	"Module Web Profile": "module_name",
	"Industry Web Profile": "industry",
}


def german_industry_name(industry):
	"""German name of an Industry Type: the title of its Industry Web Profile's German text row."""
	if not industry:
		return None
	return frappe.db.get_value("Web Profile Content", {"parenttype": "Industry Web Profile", "parent": industry,
		"language": "de"}, "title") or industry


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
			self.route = self.unique_route(slugify(self.get(TITLE_FIELDS[self.doctype]) or self.name))

	def unique_route(self, base):
		"""``base``, or ``base-2``, ``base-3`` … when another record of this doctype already uses it."""
		route, counter = base, 2
		while frappe.db.exists(self.doctype, {"route": route, "name": ["!=", self.name or ""]}):
			route = f"{base}-{counter}"
			counter += 1
		return route
