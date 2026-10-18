# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.checklist_template.checklist_template import (
	create_checklist_from_template,
)


class TestChecklistTemplate(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.template = make_template()

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_item_note_is_optional(self):
		# make_template() saves one item without a Note (#1333)
		self.assertFalse(self.template.checklist_template_items[0].note)

	def test_create_requires_checklist_owner(self):
		before = frappe.db.count("Checklist")
		for owner in (None, "", "   "):
			with self.assertRaisesRegex(frappe.ValidationError, "Checklist Owner is required"):
				create_checklist_from_template(self.template.name, checklist_owner=owner)
		self.assertEqual(frappe.db.count("Checklist"), before)

	def test_create_sets_checklist_owner(self):
		name = create_checklist_from_template(
			self.template.name, title="From template", checklist_owner="Administrator"
		)
		checklist = frappe.get_doc("Checklist", name)

		self.assertEqual(checklist.checklist_owner, "Administrator")
		self.assertEqual(checklist.checklist_template, self.template.name)
		self.assertEqual(checklist.title, "From template")
		self.assertEqual(len(checklist.checklist_items), 1)
		self.assertEqual(checklist.checklist_items[0].description, "Check without a note")


def make_template():
	template = frappe.get_doc(
		{
			"doctype": "Checklist Template",
			"naming_series": "CHKT-.####",
			"title": "Test Checklist Template",
			"department": get_department(),
			"document": "ToDo",
			"checklist_template_owner": "Administrator",
			"checklist_template_items": [{"description": "Check without a note"}],
		}
	)
	template.insert()
	template.submit()
	return template


def get_department():
	return frappe.db.get_value("Department", {}, "name") or frappe.get_doc(
		{"doctype": "Department", "department_name": "Checklist Test Department"}
	).insert().name
