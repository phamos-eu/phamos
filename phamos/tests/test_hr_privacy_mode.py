# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Privacy mode of the HR Cockpit (phamos/phamos#1839): the reveal time in Phamos Settings."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import human_resources_spa
from phamos.phamos.hr import sick_leave

FIELD = "human_resources_privacy_reveal_seconds"


class TestHrPrivacyMode(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")

	def tearDown(self):
		frappe.db.rollback()

	def _save(self, seconds):
		settings = frappe.get_single(sick_leave.SETTINGS)
		settings.set(FIELD, seconds)
		settings.save(ignore_permissions=True)

	def test_default_is_two_minutes(self):
		frappe.db.set_single_value(sick_leave.SETTINGS, FIELD, None)
		self.assertEqual(human_resources_spa.get_privacy_settings(), {"reveal_seconds": 120})

	def test_setting_changes_the_time(self):
		self._save(300)
		self.assertEqual(human_resources_spa.get_privacy_settings(), {"reveal_seconds": 300})

	def test_less_than_ten_seconds_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self._save(5)
		self._save(10)
		self.assertEqual(human_resources_spa.get_privacy_settings(), {"reveal_seconds": 10})
