# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class RiskRegisterEntry(Document):
	def before_save(self):
		self._compute_risk_levels()

	def _compute_risk_levels(self):
		likelihood = _parse_level(self.likelihood)
		impl_level = _parse_level(self.implementation_severity) * likelihood
		comp_level = _parse_level(self.company_severity) * likelihood
		self.implementation_risk_level = impl_level
		self.company_risk_level = comp_level
		# Derive the qualitative rating from the higher of the two scores
		self.risk_rating = _rating_label(max(impl_level, comp_level))


def _parse_level(value):
	if not value:
		return 0
	try:
		return int(value[0])
	except (ValueError, IndexError):
		return 0


def _rating_label(score):
	if score >= 16:
		return "Extreme"
	if score >= 10:
		return "High"
	if score >= 5:
		return "Moderate"
	if score > 0:
		return "Low"
	return ""
