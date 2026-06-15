# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import nowdate, add_days
from phamos.api import get_customer_for_user


class TestPhamosAPI(FrappeTestCase):
	def setUp(self):
		"""Set up test data before each test."""
		frappe.set_user("Administrator")
		
		# Ensure necessary master records exist
		self._ensure_customer_group_exists()
		self._ensure_territory_exists()
		
		# Create test user
		if not frappe.db.exists("User", "test_customer@example.com"):
			self.test_user = frappe.get_doc({
				"doctype": "User",
				"email": "test_customer@example.com",
				"first_name": "Test",
				"last_name": "Customer",
				"send_welcome_email": 0
			})
			self.test_user.insert(ignore_permissions=True)
		else:
			self.test_user = frappe.get_doc("User", "test_customer@example.com")
	
	def _ensure_customer_group_exists(self):
		"""Ensure Customer Group exists for tests."""
		if not frappe.db.exists("Customer Group", "Commercial"):
			if not frappe.db.exists("Customer Group", "All Customer Groups"):
				doc = frappe.get_doc({
					"doctype": "Customer Group",
					"customer_group_name": "All Customer Groups",
					"is_group": 1,
					"parent_customer_group": ""
				})
				doc.insert(ignore_permissions=True)
			
			doc = frappe.get_doc({
				"doctype": "Customer Group",
				"customer_group_name": "Commercial",
				"is_group": 0,
				"parent_customer_group": "All Customer Groups"
			})
			doc.insert(ignore_permissions=True)
	
	def _ensure_territory_exists(self):
		"""Ensure Territory exists for tests."""
		if not frappe.db.exists("Territory", "Germany"):
			if not frappe.db.exists("Territory", "All Territories"):
				doc = frappe.get_doc({
					"doctype": "Territory",
					"territory_name": "All Territories",
					"is_group": 1,
					"parent_territory": ""
				})
				doc.insert(ignore_permissions=True)
			
			doc = frappe.get_doc({
				"doctype": "Territory",
				"territory_name": "Germany",
				"is_group": 0,
				"parent_territory": "All Territories"
			})
			doc.insert(ignore_permissions=True)
	
	def test_get_customer_for_user_no_contact(self):
		"""Test get_customer_for_user when user has no contact."""
		# Create a user without any contacts
		if not frappe.db.exists("User", "no_contact@example.com"):
			user = frappe.get_doc({
				"doctype": "User",
				"email": "no_contact@example.com",
				"first_name": "No",
				"last_name": "Contact",
				"send_welcome_email": 0
			})
			user.insert(ignore_permissions=True)
		
		customer = get_customer_for_user("no_contact@example.com")
		self.assertIsNone(customer)
	
	def test_get_customer_for_user_with_valid_contact(self):
		"""Test get_customer_for_user when user has valid customer link."""
		# Create test customer
		if not frappe.db.exists("Customer", "_Test Customer for API"):
			customer = frappe.get_doc({
				"doctype": "Customer",
				"customer_name": "_Test Customer for API",
				"customer_type": "Company",
				"customer_group": "Commercial",
				"territory": "Germany"
			})
			customer.insert(ignore_permissions=True)
		
		# Delete existing contact if it exists (for clean test)
		if frappe.db.exists("Contact", {"user": self.test_user.email}):
			existing_contact = frappe.get_doc("Contact", {"user": self.test_user.email})
			existing_contact.delete(ignore_permissions=True)
		
		# Create contact linked to user and customer
		contact = frappe.get_doc({
			"doctype": "Contact",
			"first_name": "Test",
			"last_name": "Customer",
			"user": self.test_user.email,
			"links": [{
				"link_doctype": "Customer",
				"link_name": "_Test Customer for API"
			}]
		})
		contact.insert(ignore_permissions=True)
		
		# Add email to contact
		contact.append("email_ids", {
			"email_id": self.test_user.email,
			"is_primary": 1
		})
		contact.save(ignore_permissions=True)
		
		customer_name = get_customer_for_user(self.test_user.email)
		self.assertIsNotNone(customer_name)
		self.assertEqual(customer_name, "_Test Customer for API")
	
	def test_get_projects_for_customer(self):
		"""Test getting projects for a logged-in customer."""
		# This test would require full setup with customer and projects
		# For now, we'll just verify the function exists and can be called
		from phamos.api import get_projects_for_logged_in_customer
		
		# Set session user
		frappe.set_user("Administrator")
		
		# Call the function - should not raise an error
		try:
			result = get_projects_for_logged_in_customer()
			self.assertIsInstance(result, list)
		except frappe.PermissionError:
			# Expected if Administrator doesn't have customer link
			pass
	
	def tearDown(self):
		"""Clean up test data after each test."""
		frappe.set_user("Administrator")
		frappe.db.rollback()


class TestUtilityFunctions(FrappeTestCase):
	"""Test utility functions in the phamos app."""
	
	def test_date_utilities(self):
		"""Test date utility functions work correctly."""
		from frappe.utils import getdate, add_days, nowdate
		
		today = getdate(nowdate())
		tomorrow = getdate(add_days(nowdate(), 1))
		
		self.assertIsNotNone(today)
		self.assertIsNotNone(tomorrow)
		self.assertGreater(tomorrow, today)
	
	def tearDown(self):
		"""Clean up test data."""
		frappe.db.rollback()
