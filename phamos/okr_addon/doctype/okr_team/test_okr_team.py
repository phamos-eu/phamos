# Copyright (c) 2025, phamos and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestOKRTeam(FrappeTestCase):
	def test_create_okr_team(self):
		"""Test creating a basic OKR Team."""
		team = frappe.get_doc({
			"doctype": "OKR Team",
			"team_name": "Test Engineering Team",
			"team_lead": "Administrator"
		})
		team.insert()
		self.assertEqual(team.team_name, "Test Engineering Team")
		team.delete()

	def test_okr_team_name_required(self):
		"""Test that team name is required."""
		with self.assertRaises(frappe.ValidationError):
			team = frappe.get_doc({
				"doctype": "OKR Team",
				"team_lead": "Administrator"
			})
			team.insert()

	def tearDown(self):
		"""Clean up test data."""
		frappe.db.rollback()
