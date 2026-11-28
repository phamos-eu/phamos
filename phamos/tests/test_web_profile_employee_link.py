# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Website Managers link Employees to Person Web Profiles with Select permission only, and cannot
publish an Employee without consent unless they can read that Employee.

Run with
    bench --site <site> run-tests --module phamos.tests.test_web_profile_employee_link
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_years, nowdate

from phamos.web_profile.setup import ensure_employee_select_permission

USER = "wp-website-manager@example.com"


class TestWebProfileEmployeeLink(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		ensure_employee_select_permission()
		if not frappe.db.exists("User", USER):
			frappe.get_doc({
				"doctype": "User", "email": USER, "first_name": "Webby", "send_welcome_email": 0,
				"roles": [{"role": "Website Manager"}],
			}).insert(ignore_permissions=True)
		company = frappe.defaults.get_global_default("company") or frappe.get_all("Company", pluck="name", limit=1)[0]
		cls.employee = frappe.get_doc({
			"doctype": "Employee", "first_name": "Linka", "last_name": "Webprofil", "company": company,
			"gender": frappe.get_all("Gender", pluck="name", limit=1)[0], "date_of_birth": "1990-01-01",
			"date_of_joining": add_years(nowdate(), -2), "status": "Active",
		}).insert(ignore_permissions=True).name

	def setUp(self):
		frappe.db.savepoint("employee_link")  # one profile per Employee: each test starts without one

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="employee_link")

	def _profile(self, **values):
		return frappe.get_doc({"doctype": "Person Web Profile", "party_type": "Employee", "party": self.employee,
			**values})

	def test_website_manager_can_select_but_not_read_employees(self):
		frappe.set_user(USER)
		self.assertTrue(frappe.has_permission("Employee", "select"))
		self.assertFalse(frappe.has_permission("Employee", "read", self.employee))
		frappe.client.validate_link("Employee", self.employee)  # the link field accepts the value

	def test_website_manager_prepares_but_cannot_publish_without_consent(self):
		frappe.set_user(USER)
		profile = self._profile().insert()
		profile.published = 1
		self.assertRaises(frappe.ValidationError, profile.save)

	def test_website_manager_publishes_with_consent(self):
		frappe.set_user(USER)
		profile = self._profile(published=1, publication_consent=1, publication_consent_date=nowdate()).insert()
		self.assertTrue(profile.published)

	def test_hr_publishes_without_consent_and_website_manager_keeps_editing(self):
		profile = self._profile(published=1).insert()  # Administrator can read the Employee
		frappe.set_user(USER)
		profile.reload()
		profile.roles = "Consultant"
		profile.save()  # already published: no consent needed for an edit
		self.assertEqual(profile.roles, "Consultant")

	def test_website_manager_cannot_name_an_anonymous_profile_without_consent(self):
		profile = self._profile(published=1, publish_as="Anonymous").insert()
		frappe.set_user(USER)
		profile.reload()
		profile.publish_as = "Named"
		self.assertRaises(frappe.ValidationError, profile.save)
