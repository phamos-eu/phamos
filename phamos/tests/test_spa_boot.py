# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""SPA boot language and translations (#1605)."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.www import spa_boot

# Words Frappe, ERPNext or HRMS already translate, where the Personal Cockpit wants its own
# German (#1765). They live in the cockpit-only table, never in the table Desk reads.
COCKPIT_ONLY = {
	"Check-in": "Einstempeln",
	"Check-out": "Ausstempeln",
	"Done": "Erledigt",
	"Gantt": "Gantt",
	"Hours": "Stunden",
	"In": "Ein",
	"Issues": "Anfragen",
	"Other": "Sonstiges",
	"Pause": "Pause",
	"Schedule": "Einplanen",
	"Start": "Start",
	"Stop": "Stoppen",
	"Task": "Aufgabe",
	"ToDo": "ToDo",
	"Undo": "Rückgängig",
	"{0} h": "{0} Std.",
	"{0}d": "{0} T",
}
# Only for the cockpits, but not about Desk: phamos's own older Desk row says "Uhrzeit".
COCKPIT_EXTRA = {"Time": "Zeit"}


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

	def test_desk_keeps_its_own_german(self):
		# phamos's Desk table must not replace what the other apps already translate (#1765).
		from frappe.translate import get_translations_from_apps

		others = [app for app in frappe.get_installed_apps() if app != "phamos"]
		desk = get_translations_from_apps("de", others)
		phamos_desk = get_translations_from_apps("de", ["phamos"])
		for word in [*COCKPIT_ONLY, "Resolved", "Working", "Pending Review"]:
			if word in desk and word in phamos_desk:
				self.assertEqual(phamos_desk[word], desk[word], word)

	def test_cockpit_keeps_its_wording(self):
		messages = spa_boot.spa_translations("de")
		for word, german in {**COCKPIT_ONLY, **COCKPIT_EXTRA}.items():
			self.assertEqual(messages.get(word), german, word)
