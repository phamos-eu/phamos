# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _

from phamos.web_profile.document import WebProfileDocument


class StakeholderWebProfile(WebProfileDocument):
	"""Public profile of a customer, partner or other stakeholder. Facts are mirrored from the party;
	without recorded approval to be named the page is rendered anonymously (sections.load_stakeholders)."""

	def validate(self):
		super().validate()
		existing = frappe.db.get_value("Stakeholder Web Profile", {"party_type": self.party_type, "party": self.party,
			"stakeholder_type": self.stakeholder_type, "name": ["!=", self.name]})
		if existing:
			frappe.throw(_("{0} already has a {1} profile: {2}").format(self.party_name, _(self.stakeholder_type), existing))
		if self.key_person and frappe.db.get_value("Person Web Profile", self.key_person, ["party_type", "party"]) != (self.party_type, self.party):
			frappe.throw(_("The key contact must be a Person Web Profile of {0}.").format(self.party_name))
