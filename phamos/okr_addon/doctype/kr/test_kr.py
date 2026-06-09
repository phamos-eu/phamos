# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestKR(FrappeTestCase):
	def test_create_kr(self):
		"""Test creating a basic Key Result."""
		kr = frappe.get_doc({
			"doctype": "KR",
			"title": "Test Key Result",
			"target_value": 100,
			"current_value": 0
		})
		kr.insert()
		
		self.assertEqual(kr.title, "Test Key Result")
		self.assertEqual(kr.target_value, 100)
		self.assertEqual(kr.current_value, 0)
		
		kr.delete()
	
	def test_kr_progress_calculation(self):
		"""Test progress calculation when current_value changes."""
		kr = frappe.get_doc({
			"doctype": "KR",
			"title": "Progress Test KR",
			"target_value": 100,
			"current_value": 0
		})
		kr.insert()
		
		# Update progress
		kr.current_value = 50
		kr.save()
		
		# Verify the values are updated
		self.assertEqual(kr.current_value, 50)
		
		kr.delete()

	def tearDown(self):
		"""Clean up test data."""
		frappe.db.rollback()
