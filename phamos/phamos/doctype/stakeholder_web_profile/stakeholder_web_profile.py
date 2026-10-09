# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.utils import strip_html

from phamos.web_profile.document import WebProfileDocument, german_industry_name
from phamos.web_profile.utils import identifying_terms, slug_contains, slugify

# German fallback slug per stakeholder type when neither a title nor an industry is known.
TYPE_SLUGS = {"Customer": "kunde", "Partner": "partner"}


class StakeholderWebProfile(WebProfileDocument):
	"""Public profile of a customer, partner or other stakeholder. Facts are mirrored from the party.
	*Publish As* decides between a named and an anonymous page (sections.load_stakeholders); named
	needs the recorded approval, anonymous texts must not name the stakeholder (phamos/phamos#1506).
	The URL is neutral from the start and the same for both (phamos/phamos#1512)."""

	def validate(self):
		super().validate()
		existing = frappe.db.get_value("Stakeholder Web Profile", {"party_type": self.party_type, "party": self.party,
			"stakeholder_type": self.stakeholder_type, "name": ["!=", self.name]})
		if existing:
			frappe.throw(_("{0} already has a {1} profile: {2}").format(self.party_name, _(self.stakeholder_type), existing))
		if self.key_person and frappe.db.get_value("Person Web Profile", self.key_person, ["party_type", "party"]) != (self.party_type, self.party):
			frappe.throw(_("The key contact must be a Person Web Profile of {0}.").format(self.party_name))
		self.validate_publish_as()

	def validate_publish_as(self):
		if self.publish_as == "Named":
			if not self.naming_approved:
				frappe.throw(_("{0} can only be published named with their recorded approval to be named.").format(self.party_name))
			return
		for row in self.get("translations") or []:
			text = " ".join(strip_html(row.get(f) or "") for f in ("title", "summary", "content"))
			term = next((t for t in self.identifying_terms() if re.search(rf"(?<!\w){re.escape(t)}(?!\w)", text, re.IGNORECASE)), None)
			if term:
				frappe.throw(_("Row {0} ({1}) mentions \"{2}\". An anonymous page must not name the stakeholder: remove it from the text or publish as Named.").format(row.idx, row.language, term))

	def set_route(self):
		"""One neutral URL, generated once at creation and kept when the stakeholder is named or
		anonymised later (phamos/phamos#1512). It never contains the stakeholder's name or domain."""
		if self.route:
			self.route = slugify(self.route)
			if slug_contains(self.route, self.identifying_terms()):
				frappe.throw(_("The route \"{0}\" names the stakeholder. Choose a neutral one or leave it empty to generate it.").format(self.route))
			return
		base = next((slug for slug in self.route_candidates() if slug and not slug_contains(slug, self.identifying_terms())),
			TYPE_SLUGS.get(self.stakeholder_type, "stakeholder"))
		self.route = self.unique_route(base)

	def route_candidates(self):
		german_title = next((row.title for row in self.get("translations") or [] if row.language == "de" and row.title), None)
		return [slugify(german_title), slugify(" ".join(filter(None, [german_industry_name(self.industry), self.region])))]

	def identifying_terms(self):
		return identifying_terms(self.party_name, self.website)
