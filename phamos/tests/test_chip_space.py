# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space slice 1 (#2054): my own chip's remembered position and the dummy chips."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import chip_space


class ChipSpaceTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.defaults.clear_user_default(chip_space.POSITION_KEY)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def test_spawn_when_nothing_is_stored(self):
		space = chip_space.get_space()
		self.assertEqual((space["me"]["x"], space["me"]["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))
		self.assertEqual((space["cols"], space["rows"]), (chip_space.COLS, chip_space.ROWS))
		self.assertEqual(space["me"]["user"], "Administrator")

	def test_free_position_round_trip(self):
		chip_space.save_my_position(3.456, "7.1")
		me = chip_space.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (3.46, 7.1))

	def test_clamped_to_the_grid(self):
		self.assertEqual(chip_space.save_my_position(-5, 999), {"x": 0.0, "y": chip_space.ROWS - 1.0})
		self.assertEqual(chip_space.save_my_position("abc", "nan"), {"x": 0.0, "y": 0.0})

	def test_broken_stored_value_falls_back_to_spawn(self):
		frappe.defaults.set_user_default(chip_space.POSITION_KEY, "not json")
		me = chip_space.get_space()["me"]
		self.assertEqual((me["x"], me["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))

	def test_dummies_from_site_config(self):
		dummies = [{"user": "Guest", "x": 5, "y": 6}, {"user": "Administrator", "x": 1, "y": 1}, {"user": "nobody@example.com"}, "junk"]
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: dummies}):
			others = chip_space.get_space()["others"]
		# Guest is an enabled user; myself and unknown users are left out.
		self.assertEqual([(o["user"], o["x"], o["y"]) for o in others], [("Guest", 5.0, 6.0)])

	def test_no_dummies_without_site_config(self):
		with patch.dict(frappe.conf, {chip_space.DUMMIES_CONF_KEY: None}):
			self.assertEqual(chip_space.get_space()["others"], [])

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			chip_space.get_space()
		with self.assertRaises(frappe.PermissionError):
			chip_space.save_my_position(1, 1)
