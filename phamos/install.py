# Copyright (c) 2026, phamos.eu and Contributors
# License: MIT

import frappe


def before_tests():
	"""Set up test data before running tests."""
	frappe.clear_cache()
	
	# Handle custom mandatory fields that conflict with test records
	make_custom_fields_optional_for_tests()
	
	# Create necessary master records for tests
	# Note: Company is created by ERPNext's test records
	create_warehouse_types()
	create_opportunity_types()
	create_customer_groups()
	create_territories()
	create_activity_types()
	create_employment_types()
	create_departments()
	
	frappe.db.commit()


def make_custom_fields_optional_for_tests():
	"""Temporarily make custom mandatory fields optional during tests."""
	# Make project_owner not mandatory during tests
	if frappe.db.exists("Custom Field", "Project-project_owner"):
		frappe.db.set_value("Custom Field", "Project-project_owner", "reqd", 0)
	
	# Make OKR fields not mandatory during tests
	okr_meta = frappe.get_meta("OKR")
	for field in ["okr_type", "specific_okr_type"]:
		if okr_meta.has_field(field):
			okr_field = okr_meta.get_field(field)
			if okr_field and okr_field.reqd:
				frappe.db.sql("""
					UPDATE `tabDocField`
					SET reqd = 0
					WHERE parent = 'OKR' AND fieldname = %s
				""", (field,))
	
	# Clear meta cache to reload field definitions
	frappe.clear_cache(doctype="OKR")


def create_warehouse_types():
	"""Create standard Warehouse Types required by ERPNext."""
	warehouse_types = [
		"Transit",
		"Stores",
		"Work In Progress",
		"Finished Goods",
		"Sample",
		"Scrap"
	]
	
	for warehouse_type in warehouse_types:
		if not frappe.db.exists("Warehouse Type", warehouse_type):
			try:
				doc = frappe.get_doc({
					"doctype": "Warehouse Type",
					"name": warehouse_type
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass  # Already exists


def create_opportunity_types():
	"""Create Opportunity Types."""
	opportunity_types = [
		"Sales",
		"Support",
		"Maintenance",
		"Vertrieb"  # German for "Sales"
	]
	
	for opp_type in opportunity_types:
		if not frappe.db.exists("Opportunity Type", opp_type):
			try:
				doc = frappe.get_doc({
					"doctype": "Opportunity Type",
					"name": opp_type
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass  # Already exists


def create_customer_groups():
	"""Create Customer Groups."""
	customer_groups = [
		{"name": "Commercial", "is_group": 0, "parent_customer_group": "All Customer Groups"},
		{"name": "Government", "is_group": 0, "parent_customer_group": "All Customer Groups"},
		{"name": "Non Profit", "is_group": 0, "parent_customer_group": "All Customer Groups"}
	]
	
	# Ensure root group exists
	if not frappe.db.exists("Customer Group", "All Customer Groups"):
		try:
			doc = frappe.get_doc({
				"doctype": "Customer Group",
				"customer_group_name": "All Customer Groups",
				"is_group": 1,
				"parent_customer_group": ""
			})
			doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		except frappe.DuplicateEntryError:
			pass
	
	for group in customer_groups:
		if not frappe.db.exists("Customer Group", group["name"]):
			try:
				doc = frappe.get_doc({
					"doctype": "Customer Group",
					"customer_group_name": group["name"],
					"is_group": group["is_group"],
					"parent_customer_group": group["parent_customer_group"]
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass


def create_territories():
	"""Create Territories."""
	territories = [
		{"name": "Germany", "parent_territory": "All Territories"},
		{"name": "United States", "parent_territory": "All Territories"},
		{"name": "United Kingdom", "parent_territory": "All Territories"},
		{"name": "India", "parent_territory": "All Territories"},
	]
	
	# Ensure root territory exists
	if not frappe.db.exists("Territory", "All Territories"):
		try:
			doc = frappe.get_doc({
				"doctype": "Territory",
				"territory_name": "All Territories",
				"is_group": 1,
				"parent_territory": ""
			})
			doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		except frappe.DuplicateEntryError:
			pass
	
	for territory in territories:
		if not frappe.db.exists("Territory", territory["name"]):
			try:
				doc = frappe.get_doc({
					"doctype": "Territory",
					"territory_name": territory["name"],
					"is_group": 0,
					"parent_territory": territory["parent_territory"]
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass


def create_activity_types():
	"""Create Activity Types for Timesheet."""
	activity_types = [
		"Development",
		"Testing",
		"Documentation",
		"Meeting",
		"Support",
		"Training",
		"Consulting"
	]
	
	for activity_type in activity_types:
		if not frappe.db.exists("Activity Type", activity_type):
			try:
				doc = frappe.get_doc({
					"doctype": "Activity Type",
					"activity_type": activity_type,
					"billing_rate": 0
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass


def create_employment_types():
	"""Create Employment Types for Employee."""
	employment_types = [
		"Full-time",
		"Part-time",
		"Contract",
		"Intern",
		"Probation"
	]
	
	for emp_type in employment_types:
		if not frappe.db.exists("Employment Type", emp_type):
			try:
				doc = frappe.get_doc({
					"doctype": "Employment Type",
					"employee_type_name": emp_type
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass


def create_departments():
	"""Create Departments for Employee.
	
	Note: Departments require a company field in ERPNext/HRMS.
	This function finds an existing company or creates a test company
	to associate with the departments.
	"""
	# Get or use a test company - ERPNext creates test companies during test setup
	company = frappe.db.get_value("Company", {"docstatus": ["!=", 2]}, "name")
	
	if not company:
		# If no company exists, create a minimal one for tests
		try:
			company_doc = frappe.get_doc({
				"doctype": "Company",
				"company_name": "_Test Company",
				"abbr": "_TC",
				"default_currency": "USD",
				"country": "United States"
			})
			company_doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			company = company_doc.name
		except Exception:
			# If company creation fails, skip department creation
			return
	
	departments = [
		"Engineering",
		"Sales",
		"Marketing",
		"Human Resources",
		"Finance",
		"Operations"
	]
	
	for dept in departments:
		if not frappe.db.exists("Department", dept):
			try:
				doc = frappe.get_doc({
					"doctype": "Department",
					"department_name": dept,
					"company": company
				})
				doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
			except frappe.DuplicateEntryError:
				pass
			except Exception:
				# Skip if department creation fails
				pass
