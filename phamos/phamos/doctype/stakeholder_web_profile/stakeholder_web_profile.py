# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import re
from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.utils import strip_html

from phamos.web_profile.document import WebProfileDocument
from phamos.web_profile.utils import slugify

# German fallback slug per stakeholder type when neither a title nor an industry is known.
TYPE_SLUGS = {"Customer": "kunde", "Partner": "partner"}
# Legal forms dropped to find the bare company name ("Nordwerk Maschinenbau GmbH" -> "Nordwerk Maschinenbau").
LEGAL_FORMS = re.compile(
	r"(&\s*co\.?|\b(gmbh|mbh|ag|kg|kgaa|ohg|gbr|ug|se|e\.\s?k\.|ltd|llc|inc|pvt|plc|corp|s\.a|s\.r\.l|b\.v)\b)\.?",
	re.IGNORECASE,
)


class StakeholderWebProfile(WebProfileDocument):
	"""Public profile of a customer, partner or other stakeholder. Facts are mirrored from the party.
	*Publish As* decides between a named and an anonymous page (sections.load_stakeholders); named
	needs the recorded approval, anonymous texts must not name the stakeholder (phamos/phamos#1506)."""

	def validate(self):
		super().validate()
		existing = frappe.db.get_value("Stakeholder Web Profile", {"party_type": self.party_type, "party": self.party,
			"stakeholder_type": self.stakeholder_type, "name": ["!=", self.name]})
		if existing:
			frappe.throw(_("{0} already has a {1} profile: {2}").format(self.party_name, _(self.stakeholder_type), existing))
		if self.key_person and frappe.db.get_value("Person Web Profile", self.key_person, ["party_type", "party"]) != (self.party_type, self.party):
			frappe.throw(_("The key contact must be a Person Web Profile of {0}.").format(self.party_name))
		self.validate_publish_as()
		self.set_anonymous_route()

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

	def set_anonymous_route(self):
		"""Neutral, stable URL slug of the anonymous page (phamos/phamos#1507): generated once while the
		profile is anonymous, editable, never containing the stakeholder's name."""
		if self.anonymous_route:
			self.anonymous_route = slugify(self.anonymous_route)
			if self.names_stakeholder(self.anonymous_route):
				frappe.throw(_("The anonymous route \"{0}\" names the stakeholder. Choose a neutral one or leave it empty to generate it.").format(self.anonymous_route))
			if self.route_taken(self.anonymous_route):
				frappe.throw(_("The anonymous route \"{0}\" is already used by another stakeholder page.").format(self.anonymous_route))
			return
		if self.publish_as == "Named":
			return
		base = next((slug for slug in self.anonymous_route_candidates() if slug and not self.names_stakeholder(slug)),
			TYPE_SLUGS.get(self.stakeholder_type, "stakeholder"))
		self.anonymous_route, counter = base, 2
		while self.route_taken(self.anonymous_route):
			self.anonymous_route = f"{base}-{counter}"
			counter += 1

	def anonymous_route_candidates(self):
		german_title = next((row.title for row in self.get("translations") or [] if row.language == "de" and row.title), None)
		industry = None
		if self.industry:
			industry = frappe.db.get_value("Web Profile Content", {"parenttype": "Industry Web Profile",
				"parent": self.industry, "language": "de"}, "title") or self.industry
		return [slugify(german_title), slugify(" ".join(filter(None, [industry, self.region])))]

	def names_stakeholder(self, slug):
		padded = f"-{slug}-"
		return any(f"-{term}-" in padded for term in map(slugify, self.identifying_terms()) if term)

	def route_taken(self, slug):
		if slug == self.route:
			return True
		return bool(frappe.db.get_value("Stakeholder Web Profile",
			{"name": ["!=", self.name or ""], "route": slug}) or frappe.db.get_value("Stakeholder Web Profile",
			{"name": ["!=", self.name or ""], "anonymous_route": slug}))

	def identifying_terms(self):
		"""Name, name without legal form, website domain and its first label (if specific enough)."""
		terms = []
		name = " ".join((self.party_name or "").split())
		if name:
			terms.append(name)
			bare = " ".join(LEGAL_FORMS.sub(" ", name).replace(",", " ").split()).strip(" -&")
			if len(bare) >= 3 and bare != name:
				terms.append(bare)
		website = (self.website or "").strip()
		if website:
			host = (urlparse(website if "://" in website else "https://" + website).hostname or "").removeprefix("www.")
			if host:
				terms.append(host)
				label = host.split(".")[0]
				if len(label) >= 4:
					terms.append(label)
		return terms
