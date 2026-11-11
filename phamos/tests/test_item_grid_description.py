# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Description column in the item tables (#1858): property setters from phamos.setup.item_grid."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.setup import item_grid


class TestItemGridDescription(FrappeTestCase):
	def setUp(self):
		item_grid.after_migrate()

	def tearDown(self):
		for doctype in item_grid.ITEM_GRID_COLUMNS:
			frappe.clear_cache(doctype=doctype)

	def grid_columns(self, doctype):
		"""{fieldname: columns} of the fields shown in the grid."""
		meta = frappe.get_meta(doctype, cached=False)
		return {df.fieldname: df.columns for df in meta.fields if df.in_list_view}

	def test_description_is_a_grid_column_everywhere(self):
		for doctype in item_grid.ITEM_GRID_COLUMNS:
			with self.subTest(doctype=doctype):
				self.assertEqual(self.grid_columns(doctype).get("description"), 3)

	def test_widths_fit_the_grid(self):
		for doctype, columns in item_grid.ITEM_GRID_COLUMNS.items():
			with self.subTest(doctype=doctype):
				self.assertLessEqual(sum(columns.values()), 10)
				shown = self.grid_columns(doctype)
				for fieldname, width in columns.items():
					self.assertEqual(shown.get(fieldname), width, fieldname)

	def test_delivery_note_rate_leaves_the_grid(self):
		self.assertNotIn("rate", self.grid_columns("Delivery Note Item"))

	def test_running_twice_keeps_one_setter_per_property(self):
		item_grid.after_migrate()
		for doctype, fieldname, prop, _value, _type in item_grid.get_property_setters():
			count = frappe.db.count(
				"Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": prop}
			)
			self.assertEqual(count, 1, f"{doctype}.{fieldname}.{prop}")

	def test_hand_made_change_is_reset(self):
		filters = {"doc_type": "Quotation Item", "field_name": "description", "property": "columns"}
		frappe.db.set_value("Property Setter", frappe.db.get_value("Property Setter", filters), "value", "5")
		item_grid.after_migrate()
		self.assertEqual(frappe.db.get_value("Property Setter", filters, "value"), "3")
		self.assertEqual(frappe.db.get_value("Property Setter", filters, "module"), "Phamos")
