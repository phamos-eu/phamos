# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import IntegrationTestCase


class TestRiskRegisterEntry(IntegrationTestCase):
	def _make(self, impl_sev, comp_sev, likelihood):
		doc = frappe.get_doc({
			"doctype": "Risk Register Entry",
			"open_date": "2026-07-15",
			"risk_description": "Test risk",
			"impact_description": "Test impact",
			"status": "Not Started",
			"implementation_severity": impl_sev,
			"company_severity": comp_sev,
			"likelihood": likelihood,
		})
		doc.before_save()
		return doc

	def test_risk_level_calculation(self):
		doc = self._make("4 Major", "3 Moderate", "2 Unlikely")
		self.assertEqual(doc.implementation_risk_level, 8)
		self.assertEqual(doc.company_risk_level, 6)

	def test_risk_rating_extreme(self):
		doc = self._make("5 Catastrophic", "5 Catastrophic", "5 Certain")
		self.assertEqual(doc.risk_rating, "Extreme")

	def test_risk_rating_high(self):
		doc = self._make("5 Catastrophic", "2 Minor", "3 Moderate")
		self.assertEqual(doc.risk_rating, "High")

	def test_risk_rating_moderate(self):
		doc = self._make("3 Moderate", "2 Minor", "2 Unlikely")
		self.assertEqual(doc.risk_rating, "Moderate")

	def test_risk_rating_low(self):
		doc = self._make("2 Minor", "1 Insignificant", "1 Rare")
		self.assertEqual(doc.risk_rating, "Low")

	def test_risk_level_empty_fields(self):
		doc = frappe.get_doc({
			"doctype": "Risk Register Entry",
			"open_date": "2026-07-15",
			"risk_description": "Test risk",
			"impact_description": "Test impact",
			"status": "Not Started",
		})
		doc.before_save()
		self.assertEqual(doc.implementation_risk_level, 0)
		self.assertEqual(doc.company_risk_level, 0)
		self.assertEqual(doc.risk_rating, "")
