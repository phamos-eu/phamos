# Copyright (c) 2026, phamos.eu and Contributors
# License: MIT

import frappe


def before_install():
	"""Phamos Settings links to UOM "Hour", which ERPNext creates only in the setup wizard."""
	if frappe.db.exists("DocType", "UOM") and not frappe.db.exists("UOM", "Hour"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Hour"}).insert(ignore_permissions=True)


# Roots that ERPNext test_records.json link to, but do not insert themselves.
# Same shape as a test_records.json entry: make_test_objects inserts them.
_TEST_RECORD_ROOTS = (
	(
		"UOM",
		[
			{"doctype": "UOM", "uom_name": "Nos", "must_be_whole_number": 1},
			{"doctype": "UOM", "uom_name": "Hour"},
		],
	),
	(
		"Item Group",
		[{"doctype": "Item Group", "item_group_name": "All Item Groups", "is_group": 1}],
	),
	(
		"Gender",
		[
			{"doctype": "Gender", "gender": "Male"},
			{"doctype": "Gender", "gender": "Female"},
		],
	),
	(
    "Warehouse Type",
    [{"doctype": "Warehouse Type", "name": "Transit"}],
	),
)


def _test_record_name(record):
	for key in ("uom_name", "item_group_name", "gender", "name"):
		if record.get(key):
			return record[key]


def load_test_records():
	"""Load masters the way `bench run-tests` does.

	The runner reads test_records.json and inserts those docs with make_test_objects.
	Company is loaded from ERPNext's company/test_records.json the same way, after its
	Holiday List. Gender, UOM "Nos" and Item Group "All Item Groups" are not in those
	files, so they are passed to make_test_objects in the same record shape.
	"""
	from frappe.test_runner import make_test_objects, make_test_records, make_test_records_for_doctype

	if not getattr(frappe.local, "test_objects", None):
		frappe.local.test_objects = {}

	for doctype, records in _TEST_RECORD_ROOTS:
		if not frappe.db.exists("DocType", doctype):
			continue
		# make_test_objects rolls back the transaction when a name already exists.
		missing = [row for row in records if not frappe.db.exists(doctype, _test_record_name(row))]
		if missing:
			make_test_objects(doctype, missing, commit=True)

	if frappe.db.exists("DocType", "Company") and not frappe.db.exists("Company", "_Test Company"):
		# Holiday List, then Company, from their test_records.json files.
		# make_test_records_for_doctype inserts that file only. make_test_records("Company")
		# would also build every linked DocType (Account, Warehouse, ...) before the company exists.
		make_test_records("Holiday List", commit=True)
		frappe.local.test_objects.setdefault("Company", [])
		make_test_records_for_doctype("Company", commit=True)

	if frappe.db.exists("Company", "_Test Company") and not frappe.defaults.get_global_default("company"):
		frappe.defaults.set_global_default("company", "_Test Company")


def before_tests():
	"""Set up test data before running tests."""
	frappe.clear_cache()

	# Handle custom mandatory fields that conflict with test records
	make_custom_fields_optional_for_tests()

	# Test records first, so create_departments finds "_Test Company" instead of inserting a stub.
	load_test_records()

	# Create necessary master records for tests
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
	This function finds an existing company or, on a bare site, runs
	ERPNext's setup wizard to create one.
	"""
	company = frappe.db.get_value("Company", {"docstatus": ["!=", 2]}, "name")
	
	if not company:
		# A Company inserted on its own has no Fiscal Year and a currency that doesn't
		# match the price lists, so no invoice can be submitted. ERPNext's before_tests
		# runs the setup wizard instead (what ensure_company() in the Marketing tests expects).
		from erpnext.setup.utils import before_tests as erpnext_before_tests

		# The wizard sets America/New_York; keep the site's (CI sets the container's UTC).
		time_zone = frappe.db.get_single_value("System Settings", "time_zone")
		user_time_zone = frappe.db.get_value("User", "Administrator", "time_zone")
		erpnext_before_tests()
		if time_zone:
			frappe.db.set_single_value("System Settings", "time_zone", time_zone)
			frappe.db.set_value("User", "Administrator", "time_zone", user_time_zone)
			frappe.clear_cache()
		company = frappe.db.get_value("Company", {"docstatus": ["!=", 2]}, "name")
		if not company:
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
