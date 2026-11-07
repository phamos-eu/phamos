# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase


class TestMonthlyImplementationSummary(FrappeTestCase):
	pass


class TestDeliveryNoteMonthlyImplementationSummary(FrappeTestCase):
	"""The Delivery Note shows its MIS in the "phamos" section at the top of the form."""

	def tearDown(self):
		frappe.db.rollback()

	def test_dn_created_from_mis_links_the_mis(self):
		mis = frappe.get_doc({"doctype": "Monthly Implementation Summary", "name": "_T-MIS-1"})
		dn = frappe.new_doc("Delivery Note")
		dn.append("items", {"so_detail": "_T-SOI-1"})
		mod = "phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary"
		with (
			patch("erpnext.selling.doctype.sales_order.sales_order.make_delivery_note", return_value=dn),
			patch.object(type(dn), "insert"),
			patch.object(type(dn), "run_method"),
			patch(f"{mod}._add_or_update_mis_dn_row"),
			patch(f"{mod}._mirror_dn_items_into_mis"),
			patch("frappe.db.get_value", return_value="_T-PROJ"),
		):
			mis._create_dn_for_so_hours("_T-SO-1", [{"so_detail": "_T-SOI-1", "hours": 2}], "_T-PROJ",
				skip_default_stamp=True)
		self.assertEqual(dn.custom_monthly_implementation_summary, "_T-MIS-1")

	def test_patch_fills_mis_on_existing_dns(self):
		from phamos.patches.v1_0.set_delivery_note_monthly_implementation_summary import execute

		for name in ("_T-MIS-A", "_T-MIS-B"):
			frappe.get_doc({"doctype": "Monthly Implementation Summary", "name": name}).db_insert()
		for name in ("_T-DN-ITEM", "_T-DN-ROW", "_T-DN-NONE"):
			frappe.get_doc({"doctype": "Delivery Note", "name": name}).db_insert()
		frappe.get_doc({
			"doctype": "Delivery Note Item", "name": "_T-DNI-1", "parent": "_T-DN-ITEM",
			"parenttype": "Delivery Note", "parentfield": "items",
			"custom_against_monthly_implementation_summary": "_T-MIS-A",
		}).db_insert()
		frappe.get_doc({
			"doctype": "MIS Delivery Note", "name": "_T-MDN-1", "parent": "_T-MIS-B",
			"parenttype": "Monthly Implementation Summary", "parentfield": "mis_delivery_notes",
			"delivery_note": "_T-DN-ROW",
		}).db_insert()

		execute()

		got = {n: frappe.db.get_value("Delivery Note", n, "custom_monthly_implementation_summary")
			for n in ("_T-DN-ITEM", "_T-DN-ROW", "_T-DN-NONE")}
		self.assertEqual(got, {"_T-DN-ITEM": "_T-MIS-A", "_T-DN-ROW": "_T-MIS-B", "_T-DN-NONE": None})
