# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Every section on the Issue form is open, never collapsible (#2157)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.cockpits import setup as cockpits_setup
from phamos.phriend import setup as phriend_setup


class TestIssueSectionsExpanded(FrappeTestCase):
	def setUp(self):
		# start from the ERPNext state: no Property Setter keeps a section open
		frappe.db.delete("Property Setter", {"doc_type": "Issue", "property": "collapsible"})
		frappe.clear_cache(doctype="Issue")

	def collapsible_sections(self):
		return [
			df.fieldname
			for df in frappe.get_meta("Issue", cached=False).fields
			if df.fieldtype == "Section Break" and df.collapsible
		]

	def test_setup_leaves_no_section_collapsible(self):
		phriend_setup.ensure_issue_fields()
		cockpits_setup.ensure_issue_fields()
		self.assertEqual(self.collapsible_sections(), [])

	def test_standard_sections_get_a_property_setter(self):
		cockpits_setup.ensure_issue_fields()
		setters = frappe.get_all(
			"Property Setter",
			filters={"doc_type": "Issue", "property": "collapsible"},
			fields=["field_name", "value", "module"],
		)
		by_field = {s.field_name: s for s in setters}
		# "Details" is the one ERPNext opens only on closed issues (collapsible_depends_on)
		self.assertIn("sb_details", by_field)
		self.assertEqual(by_field["sb_details"].value, "0")
		self.assertEqual(by_field["sb_details"].module, cockpits_setup.MODULE)

	def test_running_twice_keeps_one_setter_per_section(self):
		cockpits_setup.ensure_issue_fields()
		cockpits_setup.ensure_issue_fields()
		count = frappe.db.count(
			"Property Setter", {"doc_type": "Issue", "property": "collapsible", "field_name": "sb_details"}
		)
		self.assertEqual(count, 1)
