# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""SPA boot language and translations (#1605)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.www import spa_boot


class TestSpaBoot(FrappeTestCase):
	def test_english_needs_no_table(self):
		self.assertEqual(spa_boot.spa_translations("en"), {})
		self.assertEqual(spa_boot.spa_translations(None), {})

	def test_german_comes_from_phamos_only(self):
		messages = spa_boot.spa_translations("de")
		self.assertEqual(messages.get("Create"), "Erstellen")
		self.assertEqual(messages.get("{0} days to go"), "Noch {0} Tage")
		# Desk's full table is not shipped: a pure ERPNext string is not in it.
		self.assertNotIn("Sales Invoice", messages)

	def test_site_translations_override(self):
		with patch.object(spa_boot, "get_user_translations", return_value={"Create": "Anlegen"}):
			self.assertEqual(spa_boot.spa_translations("de")["Create"], "Anlegen")

	def test_boot_carries_the_language(self):
		frappe.local.lang = "de"
		self.addCleanup(setattr, frappe.local, "lang", "en")
		with patch.object(frappe.sessions, "get_csrf_token", return_value="x"):
			boot = spa_boot.get_spa_boot("/personal-cockpit")
		self.assertEqual(boot["lang"], "de")
		self.assertEqual(boot["__messages"].get("Create"), "Erstellen")
