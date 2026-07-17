# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

# import frappe
from frappe.tests.utils import FrappeTestCase


class TestLeadDataImport(FrappeTestCase):
	def test_company_name_is_inferred_from_business_email_domain(self):
		from .services.mistral import _repair_business_card_company_person_mixup

		company = _repair_business_card_company_person_mixup({
			"company_name": "",
			"emails": ["wolfram.schmidt@phamos.eu"],
			"source_type": "business_card",
		})

		self.assertEqual(company["company_name"], "Phamos")

	def test_card_email_is_prioritized_over_enriched_and_inferred_emails(self):
		from .services.mistral import _prioritize_business_card_emails

		company = _prioritize_business_card_emails({
			"source_type": "business_card",
			"website": "https://phamos.eu",
			"contact_persons": ["Wolfram Schmidt"],
			"card_emails": ["wolfram.schmidt@phamos.eu"],
			"emails": ["post@phamos.eu", "w.schmidt@phamos.eu"],
		})

		self.assertEqual(company["email"], "wolfram.schmidt@phamos.eu")
		self.assertEqual(company["emails"][0], "wolfram.schmidt@phamos.eu")
