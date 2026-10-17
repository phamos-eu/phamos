# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employment Contracts in the HR cockpit: overview KPIs, saving and access."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, nowdate

from phamos.api import employment_contracts as api
from phamos.custom_scripts.custom_python.employee_dashboard import get_employee_dashboard_data


class TestEmploymentContractsApi(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			raise unittest.SkipTest("needs a company")
		self.employee = self.make_employee("Cockpit", "Tester")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def make_employee(self, first, last):
		return (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": first,
					"last_name": last,
					"gender": frappe.db.get_value("Gender", {}, "name"),
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2020-01-01",
					"company": self.company,
					"status": "Active",
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def save(self, submit=1, **values):
		return api.save_contract(
			{
				"employee": self.employee,
				"contract_type": "Employed",
				"fte_percentage": 50,
				"yearly_gross_full_time": 60000,
				**values,
			},
			submit=submit,
		)

	def test_save_fills_company_and_currency_and_submits(self):
		contract = self.save(effective_from=add_days(nowdate(), -10))
		self.assertEqual(contract["company"], self.company)
		self.assertTrue(contract["currency"])
		self.assertEqual(contract["docstatus"], 1)
		self.assertEqual(contract["monthly_gross"], 2500)
		self.assertTrue(contract["can_record_change"])

	def test_draft_can_be_edited_then_not_after_submit(self):
		draft = self.save(submit=0, effective_from=add_days(nowdate(), -10))
		self.assertTrue(draft["can_edit"])
		updated = api.save_contract({"fte_percentage": 80}, name=draft["name"], submit=1)
		self.assertEqual(updated["weekly_hours"], 32)
		self.assertRaises(frappe.ValidationError, api.save_contract, {"fte_percentage": 90}, name=draft["name"])

	def test_overview_counts(self):
		self.save(effective_from=add_days(nowdate(), -30), valid_until=add_days(nowdate(), 20))
		upcoming_for = self.make_employee("Upcoming", "Tester")
		self.save(employee=upcoming_for, effective_from=add_days(nowdate(), 15))
		without = self.make_employee("Without", "Contract")

		overview = api.get_overview()
		ending = [c.employee for c in overview["ending_soon"]]
		upcoming = [c.employee for c in overview["upcoming"]]
		missing = [e.employee for e in overview["without_contract"]]
		self.assertIn(self.employee, ending)
		self.assertIn(upcoming_for, upcoming)
		self.assertIn(without, missing)
		self.assertNotIn(upcoming_for, missing)
		self.assertNotIn(self.employee, missing)

	def test_superseded_contract_is_not_ending_soon(self):
		self.save(effective_from=add_days(nowdate(), -30))
		self.save(effective_from=add_days(nowdate(), 10), fte_percentage=70)
		ending = [c.employee for c in api.get_overview()["ending_soon"]]
		self.assertNotIn(self.employee, ending)

	def test_hr_user_has_no_access(self):
		user = "contract-hr-user@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "HR", "send_welcome_email": 0, "roles": [{"role": "HR User"}]}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		self.assertFalse(api.get_access()["can_read"])
		self.assertRaises(frappe.PermissionError, api.get_overview)
		self.assertRaises(frappe.PermissionError, api.get_contracts)

	def test_employee_dashboard_lists_contracts(self):
		data = get_employee_dashboard_data({"transactions": []})
		self.assertIn("Employment Contract", data["transactions"][0]["items"])
