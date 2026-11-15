# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Per-user cockpit preferences: the panel layout of the record pages (#1910)."""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import cockpit_preferences as prefs

KEY = "cockpit_panel_layout"


class CockpitPreferencesTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default(KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_default_when_nothing_is_stored(self):
		self.assertEqual(prefs.get_preferences(), {KEY: {}})

	def test_round_trip_through_boot(self):
		layout = {"Issue": {"order": ["phriend", "checklists"], "collapsed": ["checklists"], "width": 420}}
		prefs.set_preference(KEY, json.dumps(layout))
		self.assertEqual(
			prefs.get_preferences()[KEY],
			{"Issue": {"order": ["phriend", "checklists"], "collapsed": ["checklists"], "expanded": [], "width": 420}},
		)

	def test_cleaning(self):
		clean = prefs._clean_panel_layout(
			{
				"Issue": {
					"order": ["a", "a", 7, "", "x" * 65, "b"],
					"collapsed": "not a list",
					"width": 99999,
					"script": "<b>",
				},
				"Lead": "not an object",
				"": {"order": ["a"]},
			}
		)
		self.assertEqual(clean, {"Issue": {"order": ["a", "b"], "collapsed": [], "expanded": [], "width": prefs.MAX_DOCK_WIDTH}})
		self.assertEqual(prefs._clean_panel_layout({"Issue": {"width": 10}})["Issue"]["width"], prefs.MIN_DOCK_WIDTH)
		self.assertNotIn("width", prefs._clean_panel_layout({"Issue": {"width": True}})["Issue"])

	def test_refuses_bad_values(self):
		for value in ("not json", "[1, 2]", json.dumps("text")):
			with self.assertRaises(frappe.ValidationError):
				prefs.set_preference(KEY, value)

	def test_refuses_oversized_layout(self):
		layout = {f"Doctype {i:03d}" + "x" * 120: {"order": [f"panel-{j}" + "y" * 50 for j in range(30)]} for i in range(30)}
		with self.assertRaises(frappe.ValidationError):
			prefs.set_preference(KEY, json.dumps(layout))

	def test_unknown_key_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			prefs.set_preference("desktop_icons", "{}")

	def test_empty_value_resets(self):
		prefs.set_preference(KEY, json.dumps({"Issue": {"width": 500}}))
		self.assertEqual(prefs.set_preference(KEY, ""), {})
		self.assertIsNone(frappe.defaults.get_user_default(KEY))
		self.assertEqual(prefs.get_preferences()[KEY], {})

	def test_bad_stored_json_falls_back(self):
		frappe.defaults.set_user_default(KEY, "{broken")
		self.assertEqual(prefs.get_preferences()[KEY], {})

	def test_per_user(self):
		prefs.set_preference(KEY, json.dumps({"Issue": {"width": 500}}))
		self.assertEqual(prefs.get_preferences(user="Guest"), {})
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			prefs.set_preference(KEY, "{}")
