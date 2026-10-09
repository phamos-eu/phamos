# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _

from phamos.web_profile.document import WebProfileDocument
from phamos.web_profile.socials import detect_platform, normalize_url
from phamos.web_profile.utils import slug_contains, slugify

# URL codes: lowercase letters and digits without look-alikes (0/o, 1/l/i).
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class PersonWebProfile(WebProfileDocument):
	"""Public /people profile of an Employee or of a contact person at a Customer, Supplier or other
	party. Facts are mirrored (phamos.web_profile.mirror); consents gate what the website may show.

	One URL, a random code fixed at creation, for the named and the anonymous page (phamos/phamos#1512)."""

	def validate(self):
		super().validate()
		self.validate_unique_person()
		self.validate_consents()
		self.validate_social_links()

	def set_route(self):
		"""One URL: a random code, generated once at creation. It never contains the name and never
		changes, also not when the profile becomes anonymous (phamos/phamos#1512)."""
		if self.route:
			self.route = slugify(self.route)
			names = [part for part in (self.full_name or "").split() if len(part) > 1]
			if slug_contains(self.route, names):
				frappe.throw(_("The route \"{0}\" contains the name. Leave it empty to generate a neutral code.").format(self.route))
			return
		while not self.route or frappe.db.exists("Person Web Profile", {"route": self.route, "name": ["!=", self.name or ""]}):
			self.route = "p-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))

	def validate_unique_person(self):
		filters = {"party_type": self.party_type, "party": self.party, "name": ["!=", self.name]}
		if self.party_type != "Employee":
			filters["contact"] = self.contact
		existing = frappe.db.get_value("Person Web Profile", filters)
		if existing:
			frappe.throw(_("{0} already has a Person Web Profile: {1}").format(self.full_name or self.party, existing))

	def validate_social_links(self):
		for row in self.profile_links:
			url = normalize_url(row.profile_link)
			if not url:
				frappe.throw(_("Row {0}: {1} is not a valid web address (https://…).").format(row.idx, row.profile_link))
			row.profile_link = url
			row.platform = row.platform or detect_platform(url)

	def validate_consents(self):
		if self.party_type != "Employee" and self.published and not self.publication_consent:
			frappe.throw(_("{0} can only be published with their recorded consent to a public profile.").format(self.full_name))
		if self.contact_consent and not self.email_id:
			frappe.throw(_("Contact via the website needs a forwarding email. Add an email to the Contact or Employee."))
		if self.party_type == "Employee":
			self.publication_consent = 0
			self.publication_consent_date = None
