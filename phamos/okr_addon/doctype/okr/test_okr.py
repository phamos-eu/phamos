# Copyright (c) 2025, Phamos and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, add_days, getdate
from phamos.okr_addon.doctype.okr.okr import get_next_okr_id, OKR_ID_PATTERN


class TestOKR(FrappeTestCase):
	def setUp(self):
		"""Set up test data before each test."""
		frappe.set_user("Administrator")
		self.test_okr_data = {
			"doctype": "OKR",
			"title": "Test OKR",
			"target_date": nowdate(),
			"owner": "Administrator"
		}

	def test_okr_id_generation(self):
		"""Test automatic OKR ID generation in YYYY-Qx-#### format."""
		okr_id = get_next_okr_id()
		self.assertIsNotNone(okr_id)
		self.assertRegex(okr_id, r"^\d{4}-Q[1-4]-\d{4}$")
		
	def test_okr_id_pattern_validation(self):
		"""Test OKR ID pattern regex."""
		valid_ids = ["2026-Q1-0001", "2025-Q4-9999", "2024-Q2-0123"]
		invalid_ids = ["2026-Q5-0001", "2026-Q1-001", "Q1-0001", "2026-0001"]
		
		for okr_id in valid_ids:
			self.assertTrue(OKR_ID_PATTERN.match(okr_id), f"Expected {okr_id} to be valid")
		
		for okr_id in invalid_ids:
			self.assertFalse(OKR_ID_PATTERN.match(okr_id), f"Expected {okr_id} to be invalid")
	
	def test_okr_id_increments_correctly(self):
		"""Test that OKR IDs increment sequentially within same quarter."""
		# Create first OKR
		okr1 = frappe.get_doc(self.test_okr_data.copy())
		okr1.insert()
		first_id = okr1.name
		
		# Create second OKR - should increment
		okr2 = frappe.get_doc(self.test_okr_data.copy())
		okr2.title = "Test OKR 2"
		okr2.insert()
		second_id = okr2.name
		
		# Extract numbers from IDs
		first_num = int(first_id.split("-")[-1])
		second_num = int(second_id.split("-")[-1])
		
		self.assertEqual(second_num, first_num + 1)
		
		# Cleanup
		okr1.delete()
		okr2.delete()
	
	def test_okr_id_with_specific_quarter(self):
		"""Test OKR ID generation for specific quarters."""
		# Q1 (January)
		q1_id = get_next_okr_id("2026-01-15")
		self.assertIn("-Q1-", q1_id)
		
		# Q2 (April)
		q2_id = get_next_okr_id("2026-04-15")
		self.assertIn("-Q2-", q2_id)
		
		# Q3 (July)
		q3_id = get_next_okr_id("2026-07-15")
		self.assertIn("-Q3-", q3_id)
		
		# Q4 (October)
		q4_id = get_next_okr_id("2026-10-15")
		self.assertIn("-Q4-", q4_id)
	
	def test_create_okr_with_valid_data(self):
		"""Test creating OKR with valid data."""
		okr = frappe.get_doc(self.test_okr_data.copy())
		okr.insert()
		
		self.assertIsNotNone(okr.name)
		self.assertEqual(okr.title, "Test OKR")
		self.assertTrue(OKR_ID_PATTERN.match(okr.name))
		
		okr.delete()
	
	def test_okr_is_group_validation(self):
		"""Test that parent OKR is marked as is_group when child is linked."""
		# Create parent OKR
		parent_okr = frappe.get_doc(self.test_okr_data.copy())
		parent_okr.title = "Parent OKR"
		parent_okr.insert()
		
		# Create child OKR
		child_okr = frappe.get_doc(self.test_okr_data.copy())
		child_okr.title = "Child OKR"
		child_okr.parent_okr = parent_okr.name
		child_okr.insert()
		
		# Reload parent and check is_group flag
		parent_okr.reload()
		self.assertEqual(parent_okr.is_group, 1)
		
		# Cleanup
		child_okr.delete()
		parent_okr.delete()

	def tearDown(self):
		"""Clean up test data after each test."""
		frappe.set_user("Administrator")
		frappe.db.rollback()
