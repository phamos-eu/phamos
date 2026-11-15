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
		tree = {
			"split": "row",
			"sizes": [0.5, 0.5],
			"children": [{"panel": "description"}, {"split": "column", "sizes": [0.6, 0.4], "children": [{"panel": "chat"}, {"panel": "checklists"}]}],
		}
		layout = {"Issue": {"tree": tree, "closed": ["checklists"], "opened": ["chat", "description"]}}
		prefs.set_preference(KEY, json.dumps(layout))
		self.assertEqual(prefs.get_preferences()[KEY], layout)

	def test_cleaning(self):
		clean = prefs._clean_panel_layout(
			{
				"Issue": {
					"closed": ["a", "a", 7, "", "x" * 65, "b"],
					"opened": "not a list",
					"script": "<b>",
					"tree": {
						"split": "row",
						"sizes": [3, "x", 1],
						"children": [
							{"panel": "a"},
							{"split": "diagonal", "children": [{"panel": "c"}]},
							{"split": "column", "children": [{"panel": "a"}, {"panel": "b"}]},
						],
					},
				},
				"Lead": "not an object",
				"": {"closed": ["a"]},
				# an old layout from the dock (#1910): nothing of it is kept but the shape
				"Task": {"order": ["x"], "width": 400},
			}
		)
		self.assertEqual(
			clean,
			{
				"Issue": {
					"closed": ["a", "b"],
					"opened": [],
					# the column kept only "b" (its "a" is a duplicate) and was replaced by it
					"tree": {"split": "row", "sizes": [0.75, 0.25], "children": [{"panel": "a"}, {"panel": "b"}]},
				},
				"Task": {"closed": [], "opened": []},
			},
		)

	def test_non_finite_sizes_count_as_missing(self):
		value = '{"Issue": {"tree": {"split": "row", "sizes": [Infinity, NaN], "children": [{"panel": "a"}, {"panel": "b"}]}}}'
		tree = prefs._clean_panel_layout(value)["Issue"]["tree"]
		self.assertEqual(tree["sizes"], [0.5, 0.5])
		json.loads(json.dumps(tree), parse_constant=lambda c: self.fail(f"{c} stored"))

	def test_deep_trees_are_cut(self):
		node = {"panel": "deepest"}
		for i in range(10):
			node = {"split": "row", "sizes": [1, 1], "children": [node, {"panel": f"p{i}"}]}
		tree = prefs._clean_panel_layout({"Issue": {"tree": node}})["Issue"]["tree"]
		self.assertNotIn("deepest", json.dumps(tree))

	def test_refuses_bad_values(self):
		for value in ("not json", "[1, 2]", json.dumps("text")):
			with self.assertRaises(frappe.ValidationError):
				prefs.set_preference(KEY, value)

	def test_refuses_oversized_layout(self):
		layout = {f"Doctype {i:03d}" + "x" * 120: {"closed": [f"panel-{j}" + "y" * 50 for j in range(30)]} for i in range(30)}
		with self.assertRaises(frappe.ValidationError):
			prefs.set_preference(KEY, json.dumps(layout))

	def test_unknown_key_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			prefs.set_preference("desktop_icons", "{}")

	def test_empty_value_resets(self):
		prefs.set_preference(KEY, json.dumps({"Issue": {"closed": ["chat"]}}))
		self.assertEqual(prefs.set_preference(KEY, ""), {})
		self.assertIsNone(frappe.defaults.get_user_default(KEY))
		self.assertEqual(prefs.get_preferences()[KEY], {})

	def test_bad_stored_json_falls_back(self):
		frappe.defaults.set_user_default(KEY, "{broken")
		self.assertEqual(prefs.get_preferences()[KEY], {})

	def test_per_user(self):
		prefs.set_preference(KEY, json.dumps({"Issue": {"closed": ["chat"]}}))
		self.assertEqual(prefs.get_preferences(user="Guest"), {})
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			prefs.set_preference(KEY, "{}")
