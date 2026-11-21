# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Chip Space slice 1 (#2054): my own chip's remembered position."""

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
		me = chip_space.get_my_position()
		self.assertEqual((me["x"], me["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))
		self.assertEqual((me["cols"], me["rows"]), (chip_space.COLS, chip_space.ROWS))
		self.assertEqual(me["user"], "Administrator")

	def test_save_and_read_back(self):
		chip_space.save_my_position(3, 7)
		me = chip_space.get_my_position()
		self.assertEqual((me["x"], me["y"]), (3, 7))

	def test_clamped_to_the_grid(self):
		self.assertEqual(chip_space.save_my_position(-5, 999), {"x": 0, "y": chip_space.ROWS - 1})
		self.assertEqual(chip_space.save_my_position("abc", None), {"x": 0, "y": 0})

	def test_broken_stored_value_falls_back_to_spawn(self):
		frappe.defaults.set_user_default(chip_space.POSITION_KEY, "not json")
		me = chip_space.get_my_position()
		self.assertEqual((me["x"], me["y"]), (chip_space.COLS // 2, chip_space.ROWS // 2))

	def test_guest_is_refused(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			chip_space.get_my_position()
		with self.assertRaises(frappe.PermissionError):
			chip_space.save_my_position(1, 1)
