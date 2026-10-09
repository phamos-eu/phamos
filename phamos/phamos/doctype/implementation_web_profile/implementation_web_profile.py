# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate

from phamos.web_profile.document import WebProfileDocument, german_industry_name
from phamos.web_profile.utils import identifying_terms, slug_contains, slugify


class ImplementationWebProfile(WebProfileDocument):
	"""Public /implementations case study. Customer is named only with recorded approval."""

	def set_route(self):
		"""One neutral URL, generated once at creation from the German industry name and the start year
		("fertigung-2023"), and kept when the customer is named or anonymised later. It never contains
		the customer's name (phamos/phamos#1512)."""
		terms = self.identifying_terms()
		if self.route:
			self.route = slugify(self.route)
			if slug_contains(self.route, terms):
				frappe.throw(_("The route \"{0}\" names the customer. Choose a neutral one or leave it empty to generate it.").format(self.route))
			return
		year = str(getdate(self.start_date).year) if self.start_date else None
		base = slugify(" ".join(filter(None, [german_industry_name(self.industry), year])))
		if not base or slug_contains(base, terms):
			base = slugify(" ".join(filter(None, ["implementierung", year])))
		self.route = self.unique_route(base)

	def identifying_terms(self):
		if not self.customer:
			return []
		name, website = frappe.db.get_value("Customer", self.customer, ["customer_name", "website"]) or (None, None)
		return identifying_terms(name or self.customer, website)
