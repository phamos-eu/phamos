# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Implementation Doctype (#1969): the library of what we built — doctypes, customizations,
reports, print formats, workflows, scripts, integrations — reusable across projects and, after
review, something we can show prospects.

Features link to entries (Implementation Feature Doctype); modules see them through their
features. Tags use Frappe's own tags (sidebar), so no field is needed for them.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class ImplementationDoctype(Document):
	def autoname(self):
		# "Delivery Trip · phamos_logistics": the same doctype name can exist in several apps
		name = self.doctype_name.strip()
		self.name = f"{name} · {self.app.strip()}" if (self.app or "").strip() else name

	def validate(self):
		if self.showcase and not self.showcase_reviewed_by:
			frappe.throw(_("Set who reviewed the entry before it can be shown to prospects."))

	@property
	def used_in_implementations(self):
		"""The implementations whose features use this entry, one per line."""
		if self.is_new():
			return ""
		features = frappe.get_all(
			"Implementation Feature Doctype",
			filters={"implementation_doctype": self.name, "parenttype": "Implementation Feature"},
			pluck="parent",
			distinct=True,
		)
		if not features:
			return ""
		implementations = frappe.get_all(
			"Implementation Feature",
			filters={"name": ["in", features], "implementation": ["is", "set"]},
			pluck="implementation",
			distinct=True,
			order_by="implementation asc",
		)
		return "\n".join(implementations)
