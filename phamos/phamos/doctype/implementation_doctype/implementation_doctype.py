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
		self.guard_showcase()

	def guard_showcase(self):
		"""The showcase flag is the confidentiality gate: nothing from a customer may reach prospects.

		Whoever sets the flag is recorded as the reviewer; nobody can name someone else. A later
		change to the description or the screenshots withdraws the flag until it is reviewed again.
		"""
		before = self.get_doc_before_save()
		if not self.showcase:
			self.showcase_reviewed_by = None
			return
		if not before or not before.showcase:
			self.showcase_reviewed_by = frappe.session.user
			return
		content_changed = (before.description or "") != (self.description or "") or [
			(row.image, row.caption) for row in before.screenshots
		] != [(row.image, row.caption) for row in self.screenshots]
		if not content_changed:
			# read_only holds only in the form: keep the recorded reviewer against API writes
			self.showcase_reviewed_by = before.showcase_reviewed_by
			return
		self.showcase = 0
		self.showcase_reviewed_by = None
		frappe.msgprint(
			_("The description or screenshots changed, so the entry is no longer a showcase. Review it and set Showcase again."),
			indicator="orange",
		)

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
		# get_list: someone who may read the library but not an implementation does not see its name
		implementations = frappe.get_list(
			"Implementation Feature",
			filters={"name": ["in", features], "implementation": ["is", "set"]},
			pluck="implementation",
			distinct=True,
			order_by="implementation asc",
		)
		return "\n".join(implementations)
