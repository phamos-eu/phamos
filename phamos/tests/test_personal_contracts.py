# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My Employment Contracts in the Personal Cockpit (phamos/phamos#1600)."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from phamos.api import personal_contracts

USER = "contract-employee@example.com"
OTHER_USER = "contract-colleague@example.com"


class TestPersonalContracts(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			raise unittest.SkipTest("needs a company")
		self.employee = self.make_employee(USER, "Own")
		self.colleague = self.make_employee(OTHER_USER, "Colleague")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_employee(self, user, first_name):
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": first_name, "send_welcome_email": 0, "roles": [{"role": "Employee"}]}
			).insert(ignore_permissions=True)
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": first_name,
					"last_name": "Tester",
					"gender": frappe.db.get_value("Gender", {}, "name"),
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": self.company,
					"status": "Active",
					"user_id": user,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def contract(self, employee, effective_from, submit=True, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Employment Contract",
				"employee": employee,
				"company": self.company,
				"contract_type": "Employed",
				"effective_from": effective_from,
				"fte_percentage": 50,
				"yearly_gross_full_time": 60000,
				"notes": "HR internal",
				**values,
			}
		).insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	def test_sees_only_own_submitted_contracts(self):
		current = self.contract(self.employee, add_days(nowdate(), -30))
		upcoming = self.contract(self.employee, add_days(nowdate(), 30), fte_percentage=80)
		self.contract(self.employee, add_days(nowdate(), 90), submit=False)
		colleague_contract = self.contract(self.colleague, add_days(nowdate(), -30))

		frappe.set_user(USER)
		data = personal_contracts.get_my_contracts()
		names = [c.name for c in data["history"]]
		self.assertEqual(data["current"].name, current.name)
		self.assertEqual([c.name for c in data["upcoming"]], [upcoming.name])
		self.assertEqual(sorted(names), sorted([current.name, upcoming.name]))
		self.assertNotIn(colleague_contract.name, names)

	def test_internal_fields_stay_hidden(self):
		self.contract(self.employee, add_days(nowdate(), -30), expense_account=None)
		frappe.set_user(USER)
		row = personal_contracts.get_my_contracts()["history"][0]
		self.assertNotIn("notes", row)
		self.assertNotIn("expense_account", row)

	def test_employee_role_still_has_no_doctype_access(self):
		self.contract(self.employee, add_days(nowdate(), -30))
		frappe.set_user(USER)
		self.assertFalse(frappe.has_permission("Employment Contract", "read"))

	def test_user_without_employee_gets_nothing(self):
		frappe.set_user("Guest")
		data = personal_contracts.get_my_contracts()
		self.assertIsNone(data["employee"])
		self.assertEqual(data["history"], [])
