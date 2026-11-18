# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Implementation Feature (#1968): what a team builds for a customer, from the first sales
conversation (Opportunity) to live use in the Implementation.

Progress is a level on the 1–6 scale of Implementation Modules, set by the PM, next to a
definition of done that phamos and the customer agree on. The share of closed GitLab issues is
shown as a hint (suggested_progress), never as the level itself.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, getdate, today

MIN_LEVEL, MAX_LEVEL = 1, 6


class ImplementationFeature(Document):
	@property
	def suggested_progress(self):
		"""Closed versus all GitLab issues linked to this feature, in percent; None without issues."""
		if self.is_new():
			return None
		states = frappe.get_all("GitLab Issue", filters={"implementation_feature": self.name}, pluck="state")
		if not states:
			return None
		return round(100 * sum(1 for state in states if state == "closed") / len(states))

	def validate(self):
		self.validate_origin()
		self.set_customer()
		self.validate_levels()
		self.validate_dates()
		self.validate_dependencies()
		self.reset_agreement_when_dod_changes()
		self.add_progress_row()

	def validate_origin(self):
		if not self.implementation and not self.opportunity:
			frappe.throw(_("A feature belongs to an Implementation or, while in sales, to an Opportunity."))

	def set_customer(self):
		if self.implementation:
			self.customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		elif self.opportunity:
			# an Opportunity's party is a Customer or a Lead; only a Customer is kept here
			party_type, party = frappe.db.get_value(
				"Opportunity", self.opportunity, ["opportunity_from", "party_name"]
			) or (None, None)
			self.customer = party if party_type == "Customer" else None

	def validate_levels(self):
		for field in ("target_level", "current_level"):
			value = self.get(field)
			if value not in (None, "", 0) and not MIN_LEVEL <= cint(value) <= MAX_LEVEL:
				frappe.throw(_("{0} must be between 1 and 6.").format(_(self.meta.get_label(field))))
		# a feature can go beyond its target only once it is live
		if (
			cint(self.target_level)
			and cint(self.current_level) > cint(self.target_level)
			and self.status != "Live"
		):
			frappe.throw(_("The current level is above the target level. Raise the target, or set the feature live."))

	def validate_dates(self):
		if self.planned_start and self.target_date and getdate(self.target_date) < getdate(self.planned_start):
			frappe.throw(_("The target date is before the planned start."))

	def validate_dependencies(self):
		seen = set()
		for row in self.depends_on:
			if row.feature == self.name:
				frappe.throw(_("A feature cannot depend on itself."))
			if row.feature in seen:
				frappe.throw(_("Feature {0} is listed twice under Depends On.").format(row.feature))
			seen.add(row.feature)
			other = frappe.db.get_value(
				"Implementation Feature", row.feature, ["implementation", "opportunity"], as_dict=True
			)
			if not other:
				frappe.throw(_("Feature {0} does not exist.").format(row.feature))
			# in sales, dependencies stay within the Opportunity; once taken over, within the Implementation
			if self.implementation and other.implementation != self.implementation:
				frappe.throw(_("Feature {0} belongs to another implementation.").format(row.feature))
			if not self.implementation and other.opportunity != self.opportunity:
				frappe.throw(_("Feature {0} belongs to another opportunity.").format(row.feature))
		if not self.is_new() and self._leads_back_here(seen):
			frappe.throw(_("These dependencies form a loop: a feature would wait for itself."))

	def _leads_back_here(self, start):
		"""Whether following Depends On from `start` reaches this feature again."""
		queue, visited = list(start), set()
		while queue:
			name = queue.pop()
			if name == self.name:
				return True
			if name in visited:
				continue
			visited.add(name)
			queue.extend(
				frappe.get_all(
					"Implementation Feature Dependency",
					filters={"parent": name, "parenttype": "Implementation Feature"},
					pluck="feature",
				)
			)
		return False

	def reset_agreement_when_dod_changes(self):
		"""A changed definition of done is no longer what the customer agreed to."""
		before = self.get_doc_before_save()
		if before and (before.definition_of_done or "") != (self.definition_of_done or ""):
			# the form sends dates as strings, the stored doc has date objects: compare as text
			agreement_changed = str(self.dod_agreed_on or "") != str(before.dod_agreed_on or "") or (
				self.dod_agreed_by or ""
			) != (before.dod_agreed_by or "")
			if not agreement_changed:
				self.dod_agreed_on = None
				self.dod_agreed_by = None

	def add_progress_row(self):
		"""One row in the history whenever the status or the current level changes."""
		before = self.get_doc_before_save()
		if before and before.status == self.status and cint(before.current_level) == cint(self.current_level):
			return
		self.append(
			"progress",
			{
				"date": today(),
				"status": self.status,
				"level": cint(self.current_level) or None,
				"by": frappe.session.user,
			},
		)


@frappe.whitelist()
def take_over_from_sales(implementation):
	"""Move the features of the won Opportunities to this Implementation (#1968).

	An Opportunity counts as won for this Implementation when one of its Quotations became a
	Sales Order linked to the Implementation (Sales Order.custom_implementation). Features keep
	their source ("Sales") and history. Returns the names of the moved features.
	"""
	frappe.has_permission("Implementation", "write", doc=implementation, throw=True)
	frappe.has_permission("Implementation Feature", "write", throw=True)
	opportunities = _won_opportunities(implementation)
	if not opportunities:
		return []
	names = frappe.get_all(
		"Implementation Feature",
		filters={"opportunity": ["in", opportunities], "implementation": ["is", "not set"]},
		pluck="name",
	)
	# Move them all first, then save each: a feature may depend on another feature of the same
	# Opportunity, and the dependency check needs both on the Implementation already.
	customer = frappe.db.get_value("Implementation", implementation, "customer")
	for name in names:
		frappe.db.set_value(
			"Implementation Feature", name, {"implementation": implementation, "customer": customer}, update_modified=False
		)
	for name in names:
		frappe.get_doc("Implementation Feature", name).save()
	return names


def _won_opportunities(implementation):
	orders = frappe.get_all(
		"Sales Order", filters={"custom_implementation": implementation, "docstatus": 1}, pluck="name"
	)
	if not orders:
		return []
	quotations = frappe.get_all(
		"Sales Order Item",
		filters={"parent": ["in", orders], "prevdoc_docname": ["is", "set"]},
		pluck="prevdoc_docname",
		distinct=True,
	)
	if not quotations:
		return []
	opportunities = frappe.get_all(
		"Quotation",
		filters={"name": ["in", quotations], "opportunity": ["is", "set"]},
		pluck="opportunity",
		distinct=True,
	)
	# An Opportunity of another customer is not taken over, even if a Quotation points to it.
	# One that came from a Lead has no customer yet and counts.
	customer = frappe.db.get_value("Implementation", implementation, "customer")
	return [
		name
		for name in opportunities
		if not (
			(party := frappe.db.get_value("Opportunity", name, ["opportunity_from", "party_name"], as_dict=True))
			and party.opportunity_from == "Customer"
			and party.party_name != customer
		)
	]
