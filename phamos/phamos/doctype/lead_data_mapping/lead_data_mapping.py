# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


DEFAULT_LEAD_DATA_FIELD_MAPPINGS = [
	("Salutation", "Here we input, Dear Sir or Madam etc."),
	("First Name", "The first name of the main contact"),
	("Middle Name", "The middle Name of the main contact, should be coherent to First Name"),
	("Last Name", "The Last Name of the main contact, should be coherent to First Name"),
	("Job Title", "Extract real role/designation written next to each contact person, e.g. CEO, Geschäftsführer, Sales Manager, Head of Marketing, Dipl.-Betriebswirt (FH). Keep titles in the same order as Contact Person and separate multiple titles with comma. Do not use legal responsibility labels such as 'Verantwortlich gemäß § 55 RStV', Impressum labels, department names, or company legal text."),
	("Organization Name", "The registered company, organisation, brand, or logo name for the lead."),
	("Email", "The primary email address for the lead. Prefer the company or contact email over generic/no-reply emails."),
	("Website", "The official website URL for the company or organisation."),
	("Mobile No", "The main mobile number for the lead or contact person."),
	("Phone", "The main telephone number for the company or contact person. Do not use fax numbers unless no phone is available."),
	("City", "The city/town from the primary postal address."),
	("State/Province", "The state, province, or region from the primary postal address."),
	("Country", "The country from the primary postal address."),
	("Address", "Extract only clean postal addresses, e.g. 'Eberhardstraße 1, 72764 Reutlingen, Germany' or 'Vogelsangstrasse 31, 72581 Dettingen/Erms, Germany'. Stop after city/country. Do not include VAT ID, sales tax identification, commercial register, legal paragraphs, website/navigation text, Datenschutz/Impressum/Recht links, phone/email labels, cookie text, or repeated duplicate variants. Prefer the complete address with country if available."),
	("Contact Person", "Human contact names only. Do not put the company or organisation name here."),
]

OLD_DEFAULT_LEAD_DATA_FIELD_MAPPINGS = {
	"Job Title": "The role, position, designation, or title of the main contact person.",
	"Address": "The visible postal address for the company or main contact. Prefer registered office/imprint addresses.",
}

PREVIOUS_DEFAULT_LEAD_DATA_FIELD_MAPPINGS = {
	"Job Title": "Extract the role/designation written next to each contact person, e.g. CEO, Geschäftsführer, Sales Manager, Head of Marketing. Keep titles in the same order as Contact Person and separate multiple titles with comma. Do not put department names or company legal text here.",
	"Address": "Extract only clean postal addresses, e.g. 'Hauptstraße 1, 74357 Bönnigheim, Germany'. Do not include VAT ID, sales tax identification, commercial register, legal paragraphs, phone/email labels, cookie text, navigation text, or repeated duplicate variants. Prefer the complete address with country if available.",
}


class LeadDataMapping(Document):
	pass


def ensure_default_lead_data_mapping():
	if not frappe.db.exists("DocType", "Lead Data Mapping"):
		return

	doc = frappe.get_single("Lead Data Mapping")

	existing_fields = {row.lead_data_field for row in doc.lead_data_field_mapping or []}
	for field, condition in DEFAULT_LEAD_DATA_FIELD_MAPPINGS:
		if field in existing_fields:
			continue
		doc.append("lead_data_field_mapping", {
			"lead_data_field": field,
			"conditions": condition,
		})
	for row in doc.lead_data_field_mapping or []:
		field = row.lead_data_field
		default_condition = dict(DEFAULT_LEAD_DATA_FIELD_MAPPINGS).get(field)
		if not default_condition:
			continue
		if (
			not row.conditions
			or row.conditions == OLD_DEFAULT_LEAD_DATA_FIELD_MAPPINGS.get(field)
			or row.conditions == PREVIOUS_DEFAULT_LEAD_DATA_FIELD_MAPPINGS.get(field)
		):
			row.conditions = default_condition

	doc.save(ignore_permissions=True)
