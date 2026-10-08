# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import secrets

import frappe
from frappe import _

from phamos.web_profile.document import WebProfileDocument
from phamos.web_profile.socials import detect_platform, normalize_url
from phamos.web_profile.utils import slugify

# Anonymous codes: lowercase letters and digits without look-alikes (0/o, 1/l/i).
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class PersonWebProfile(WebProfileDocument):
	"""Public /people profile of an Employee or of a contact person at a Customer, Supplier or other
	party. Facts are mirrored (phamos.web_profile.mirror); consents gate what the website may show.

	Two URLs, both fixed at creation and never containing the full name (phamos/phamos#1509): the
	named route (first name + initial of the surname) and a random anonymous route."""

	def validate(self):
		super().validate()
		self.validate_unique_person()
		self.validate_consents()
		self.validate_social_links()
		self.set_anonymous_route()

	def shown_named(self):
		"""Whether the website may show this person by name (same rule as sections.load_people)."""
		if self.publish_as == "Anonymous":
			return False
		if self.party_type != "Employee":
			return bool(self.publication_consent)
		return self.status != "Left" or bool(self.alumni_consent)

	def set_route(self):
		"""Named URL: first name + initial of the surname ("Wolfram Schmidt" -> "wolfram-s")."""
		if self.route:
			self.route = slugify(self.route)
			surname = self.surname_slug()
			if surname and f"-{surname}-" in f"-{self.route}-":
				frappe.throw(_("The route \"{0}\" contains the surname. Use the first name and the initial of the surname, e.g. \"{1}\".").format(self.route, self.short_name_slug()))
			if self.route_taken(self.route, own=self.anonymous_route):
				frappe.throw(_("The route \"{0}\" is already used by another person.").format(self.route))
			return
		base = self.short_name_slug() or "person"
		self.route, counter = base, 2
		while self.route_taken(self.route, own=self.anonymous_route):
			self.route = f"{base}-{counter}"
			counter += 1

	def set_anonymous_route(self):
		"""Anonymous URL: a random code, created once (phamos/phamos#1509)."""
		if self.published and not self.shown_named():
			self.anonymous_route_published = 1  # the anonymous URL is public from now on
		if self.anonymous_route:
			return
		while not self.anonymous_route or self.route_taken(self.anonymous_route, own=self.route):
			self.anonymous_route = "p-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))

	def name_parts(self):
		return [part for part in (self.full_name or "").split() if part]

	def short_name_slug(self):
		parts = self.name_parts()
		if not parts:
			return None
		return slugify(" ".join([parts[0], parts[-1][0]]) if len(parts) > 1 else parts[0])

	def surname_slug(self):
		parts = self.name_parts()
		surname = slugify(parts[-1]) if len(parts) > 1 else None
		return surname if surname and len(surname) > 1 else None

	def route_taken(self, slug, own=None):
		"""Used by another person (named or anonymous URL) or by this person's other URL (``own``)."""
		others = {"name": ["!=", self.name or ""]}
		return slug == own or bool(frappe.db.get_value("Person Web Profile", {**others, "route": slug})
			or frappe.db.get_value("Person Web Profile", {**others, "anonymous_route": slug}))

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
