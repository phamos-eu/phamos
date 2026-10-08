# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from phamos.web_profile.document import WebProfileDocument
from phamos.web_profile.socials import detect_platform, normalize_url


class PersonWebProfile(WebProfileDocument):
	"""Public /people profile of an Employee or of a contact person at a Customer, Supplier or other
	party. Facts are mirrored (phamos.web_profile.mirror); consents gate what the website may show."""

	def validate(self):
		super().validate()
		self.validate_unique_person()
		self.validate_consents()
		self.validate_social_links()

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
