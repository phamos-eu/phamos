# Copyright (c) 2026, phamos.eu and contributors
# See license.txt

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.employment_contract.employment_contract import (
	compute_status,
	get_active_contract,
	update_contract_statuses,
)


class TestEmploymentContract(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.company = frappe.db.get_value("Company", {}, "name")
		if not self.company:
			raise unittest.SkipTest("needs a company")
		self.employee = (
			frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": "Contract",
					"last_name": "Tester",
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

	def tearDown(self):
		frappe.db.rollback()

	def contract(self, effective_from, valid_until=None, submit=True, **values):
		doc = frappe.get_doc(
			{
				"doctype": "Employment Contract",
				"employee": self.employee,
				"company": self.company,
				"contract_type": "Employed",
				"effective_from": effective_from,
				"valid_until": valid_until,
				"fte_percentage": 50,
				"yearly_gross_full_time": 60000,
				**values,
			}
		).insert(ignore_permissions=True)
		if submit:
			doc.submit()
		return doc

	def test_employed_amounts_scale_with_fte(self):
		doc = self.contract("2030-01-01", submit=False)
		self.assertEqual(doc.weekly_hours, 20)
		self.assertEqual(doc.monthly_gross, 2500)

	def test_external_uses_agreed_monthly_amount(self):
		doc = self.contract(
			"2030-01-01", submit=False, contract_type="External", fte_percentage=50, monthly_amount=4000
		)
		self.assertEqual(doc.monthly_gross, 4000)
		self.assertEqual(doc.yearly_gross_full_time, 0)

	def test_fte_must_be_in_range(self):
		self.assertRaises(frappe.ValidationError, self.contract, "2030-01-01", submit=False, fte_percentage=0)
		self.assertRaises(frappe.ValidationError, self.contract, "2030-01-01", submit=False, fte_percentage=120)

	def test_new_contract_closes_open_predecessor(self):
		first = self.contract("2025-01-01")
		second = self.contract("2025-04-01", fte_percentage=70)
		first.reload()
		self.assertEqual(str(first.valid_until), "2025-03-31")
		self.assertEqual(first.superseded_by, second.name)
		self.assertEqual(second.weekly_hours, 28)

	def test_overlap_with_closed_contract_is_rejected(self):
		self.contract("2025-01-01", "2025-06-30")
		self.assertRaises(frappe.ValidationError, self.contract, "2025-03-01")

	def test_cancel_restores_superseded_contract(self):
		first = self.contract("2025-01-01")
		second = self.contract("2025-04-01")
		second.cancel()
		first.reload()
		self.assertIsNone(first.valid_until)
		self.assertIsNone(first.superseded_by)

	def test_cancel_in_the_middle_keeps_chain_without_overlap(self):
		first = self.contract("2025-01-01")
		second = self.contract("2025-04-01")
		third = self.contract("2025-08-01")
		second.reload()  # submitting the third contract closed the second one
		second.cancel()
		first.reload()
		self.assertEqual(str(first.valid_until), "2025-07-31")
		self.assertEqual(first.superseded_by, third.name)

	def test_get_active_contract_by_date(self):
		self.contract("2025-01-01", fte_percentage=50)
		self.contract("2025-04-01", "2025-06-30", fte_percentage=70)
		self.contract("2025-09-01", fte_percentage=100)
		self.assertIsNone(get_active_contract(self.employee, "2024-12-31"))
		self.assertEqual(get_active_contract(self.employee, "2025-02-15").fte_percentage, 50)
		self.assertEqual(get_active_contract(self.employee, "2025-05-01").fte_percentage, 70)
		# After the fixed-term change the earlier 50 % terms resume until the September contract.
		self.assertEqual(get_active_contract(self.employee, "2025-07-15").fte_percentage, 50)
		self.assertEqual(get_active_contract(self.employee, "2030-01-01").fte_percentage, 100)
		self.assertNotIn("yearly_gross_full_time", get_active_contract(self.employee, "2025-02-15"))

	def test_status(self):
		self.assertEqual(compute_status(0, "2025-01-01", None), "Draft")
		self.assertEqual(compute_status(2, "2025-01-01", None), "Cancelled")
		self.assertEqual(compute_status(1, "2025-02-01", None, on_date="2025-01-15"), "Upcoming")
		self.assertEqual(compute_status(1, "2025-01-01", "2025-01-31", on_date="2025-01-15"), "Active")
		self.assertEqual(compute_status(1, "2025-01-01", "2025-01-31", on_date="2025-02-01"), "Expired")

	def test_daily_job_expires_contracts(self):
		doc = self.contract("2020-01-01", "2020-12-31")
		frappe.db.set_value("Employment Contract", doc.name, "status", "Active")
		update_contract_statuses()
		self.assertEqual(frappe.db.get_value("Employment Contract", doc.name, "status"), "Expired")

	def test_relieving_date_caps_open_end(self):
		frappe.db.set_value("Employee", self.employee, "relieving_date", "2025-12-31")
		doc = self.contract("2025-01-01", submit=False)
		self.assertEqual(str(doc.valid_until), "2025-12-31")
		self.assertRaises(frappe.ValidationError, self.contract, "2026-02-01", submit=False)

	def test_temporary_change_resumes_open_terms(self):
		original = self.contract("2025-01-01", fte_percentage=100)
		temporary = self.contract("2025-03-01", "2025-04-30", fte_percentage=50)
		original.reload()
		self.assertEqual(str(original.valid_until), "2025-02-28")

		continuation = frappe.get_doc("Employment Contract", {"continuation_of": temporary.name, "docstatus": 1})
		self.assertEqual(str(continuation.effective_from), "2025-05-01")
		self.assertIsNone(continuation.valid_until)
		self.assertEqual(continuation.fte_percentage, 100)
		self.assertEqual(get_active_contract(self.employee, "2025-03-15").fte_percentage, 50)
		self.assertEqual(get_active_contract(self.employee, "2025-06-01").fte_percentage, 100)

	def test_cancelling_temporary_change_reopens_original(self):
		original = self.contract("2025-01-01", fte_percentage=100)
		temporary = self.contract("2025-03-01", "2025-04-30", fte_percentage=50)
		continuation = frappe.db.get_value("Employment Contract", {"continuation_of": temporary.name}, "name")
		temporary.reload()
		temporary.cancel()
		original.reload()
		self.assertEqual(frappe.db.get_value("Employment Contract", continuation, "docstatus"), 2)
		self.assertIsNone(original.valid_until)
		self.assertIsNone(original.superseded_by)

	def test_no_continuation_after_relieving_date(self):
		self.contract("2025-01-01")
		frappe.db.set_value("Employee", self.employee, "relieving_date", "2025-04-30")
		temporary = self.contract("2025-03-01", "2025-04-30", fte_percentage=50)
		self.assertFalse(frappe.db.exists("Employment Contract", {"continuation_of": temporary.name}))

	def test_relieving_date_ends_open_contract(self):
		open_contract = self.contract("2025-01-01")
		later = self.contract("2026-01-01")  # starts after the relieving date: left alone
		employee = frappe.get_doc("Employee", self.employee)
		employee.relieving_date = "2025-09-30"
		employee.save(ignore_permissions=True)

		open_contract.reload()
		self.assertEqual(str(open_contract.valid_until), "2025-09-30")
		self.assertEqual(open_contract.status, "Expired")
		self.assertIsNone(frappe.db.get_value("Employment Contract", later.name, "valid_until"))
