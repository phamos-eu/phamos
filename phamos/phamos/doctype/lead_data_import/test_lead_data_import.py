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
			"contact_persons": ["Website Contact"],
			"card_emails": ["wolfram.schmidt@phamos.eu"],
			"card_phones": ["+49 7131 618 865-0"],
			"card_mobile_numbers": ["+49 171 640 93 60"],
			"card_contact_persons": ["Christoph Winkler"],
			"card_job_title": "Rechtsanwalt",
			"emails": ["post@phamos.eu", "w.schmidt@phamos.eu"],
			"phones": ["+49 999 12345"],
			"job_title": "Sekretariatsleitung",
		})

		self.assertEqual(company["email"], "wolfram.schmidt@phamos.eu")
		self.assertEqual(company["emails"], ["wolfram.schmidt@phamos.eu"])
		self.assertEqual(company["phones"], ["+49 7131 618 865-0"])
		self.assertEqual(company["mobile_numbers"], ["+49 171 640 93 60"])
		self.assertEqual(company["contact_persons"], ["Christoph Winkler"])
		self.assertEqual(company["job_title"], "Rechtsanwalt")

	def test_website_enrichment_does_not_change_any_business_card_field(self):
		from .services.enrichment import _attach_business_card_research

		card = {
			"source_type": "business_card",
			"company_name": "Legasus",
			"website": "https://legasus.de",
			"addresses": ["Lise-Meitner-Straße 14, 74074 Heilbronn"],
			"contact_persons": ["Christoph Winkler"],
			"job_title": "Rechtsanwalt",
		}
		website_data = {
			"company_name": "Legasus Rechtsanwälte PartG mbB",
			"addresses": ["Another website address"],
			"contact_persons": ["Heike Kayser"],
			"job_title": "Sekretariatsleitung",
		}

		result = _attach_business_card_research(card, website_data, ["https://legasus.de/impressum"])
		for key, value in card.items():
			self.assertEqual(result[key], value)
		self.assertEqual(result["website_research"]["contact_persons"], ["Heike Kayser"])
		self.assertEqual(result["website_research"]["sources"], ["https://legasus.de/impressum"])

	def test_matching_website_values_correct_card_ocr_typos_only(self):
		from .services.enrichment import _reconcile_card_with_matching_website_research

		card = {
			"source_type": "business_card",
			"addresses": ["Lise-Meitner-Straße 14, 89081 Ulm"],
			"phones": ["+49 731 618 865 0"],
			"card_phones": ["+49 731 618 865 0"],
			"contact_persons": ["Christoph Winkler"],
		}
		website_data = {
			"addresses": [
				"Lise-Meitner-Straße 14, 74074 Heilbronn",
				"Unrelated Street 1, 89081 Ulm",
			],
			"phones": ["+49 7131 618 865-0"],
			"contact_persons": ["Heike Kayser"],
		}

		result = _reconcile_card_with_matching_website_research(card, website_data)
		self.assertEqual(result["addresses"], ["Lise-Meitner-Straße 14, 74074 Heilbronn"])
		self.assertEqual(result["phones"], ["+49 7131 618 865-0"])
		self.assertEqual(result["contact_persons"], ["Christoph Winkler"])

	def test_website_fills_only_fields_missing_from_business_card(self):
		from .services.enrichment import _fill_missing_card_fields_from_website

		card = {
			"source_type": "business_card",
			"company_name": "Phamos",
			"website": "https://phamos.eu",
			"emails": ["wolfram.schmidt@phamos.eu"],
			"phones": ["+49 176 555 190 59"],
			"contact_persons": [],
			"addresses": [],
		}
		website_data = {
			"emails": ["post@phamos.eu"],
			"phones": ["+49 7152 569 3854"],
			"contact_persons": ["Wolfram Schmidt"],
			"addresses": ["Panoramastraße 19, 72119 Ammerbuch, Germany"],
		}

		result = _fill_missing_card_fields_from_website(card, website_data)
		self.assertEqual(result["emails"], ["wolfram.schmidt@phamos.eu"])
		self.assertEqual(result["phones"], ["+49 176 555 190 59"])
		self.assertEqual(result["contact_persons"], ["Wolfram Schmidt"])
		self.assertEqual(result["addresses"], ["Panoramastraße 19, 72119 Ammerbuch, Germany"])
