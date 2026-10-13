# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""The #1453 patch moves saved cockpit settings and default-app choices to the new names."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0 import rename_hr_and_pm_cockpit_settings_fields as rename_patch

SETTINGS = rename_patch.SETTINGS_DOCTYPE


def _set_single_row(field, value):
	"""Write one raw tabSingles row, the way values were stored before the rename."""
	frappe.db.delete("Singles", {"doctype": SETTINGS, "field": field})
	frappe.qb.into("Singles").columns("doctype", "field", "value").insert(SETTINGS, field, value).run()


def _get_single_row(field):
	"""Read one raw tabSingles value, bypassing the cached single document."""
	singles = frappe.qb.DocType("Singles")
	rows = (
		frappe.qb.from_(singles)
		.select(singles.value)
		.where((singles.doctype == SETTINGS) & (singles.field == field))
		.run(pluck=True)
	)
	return rows[0] if rows else None


class TestRenameCockpitSettingsFields(FrappeTestCase):
	def setUp(self):
		# Every test changes settings rows; undo them so the site keeps its real values.
		self.addCleanup(frappe.db.rollback)
		for old_fieldname, new_fieldname in rename_patch.FIELDS.items():
			frappe.db.delete("Singles", {"doctype": SETTINGS, "field": new_fieldname})
			_set_single_row(old_fieldname, f"value of {old_fieldname}")

	def test_moves_saved_values_to_new_fields(self):
		rename_patch.execute()

		for old_fieldname, new_fieldname in rename_patch.FIELDS.items():
			with self.subTest(field=old_fieldname):
				self.assertIsNone(_get_single_row(old_fieldname))
				self.assertEqual(_get_single_row(new_fieldname), f"value of {old_fieldname}")

	def test_second_run_changes_nothing(self):
		rename_patch.execute()
		rename_patch.execute()

		for old_fieldname, new_fieldname in rename_patch.FIELDS.items():
			with self.subTest(field=old_fieldname):
				self.assertEqual(_get_single_row(new_fieldname), f"value of {old_fieldname}")

	def test_moves_default_app_for_users_and_system(self):
		frappe.db.set_value("User", "Administrator", "default_app", rename_patch.OLD_APP_NAME)
		frappe.db.set_single_value("System Settings", "default_app", rename_patch.OLD_APP_NAME)

		rename_patch.execute()

		self.assertEqual(
			frappe.db.get_value("User", "Administrator", "default_app"), rename_patch.NEW_APP_NAME
		)
		self.assertEqual(
			frappe.db.get_single_value("System Settings", "default_app"), rename_patch.NEW_APP_NAME
		)

	def test_stops_when_new_fields_are_missing(self):
		with patch("frappe.model.meta.Meta.has_field", return_value=False):
			self.assertRaises(frappe.ValidationError, rename_patch.execute)
		self.assertEqual(_get_single_row("hr_department"), "value of hr_department")
