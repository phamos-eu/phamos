# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Access scope of the Implementation Cockpit API (#1671).

A customer user sees only Implementations where one of their Contacts is a Customer stakeholder
and that are shown on the customer portal; nothing else is reachable, and internal fields never
leave the server.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api import implementation_cockpit as ic

PREFIX = "_Test IC "
USER = "ic-customer@example.com"


def _customer(name):
	if not frappe.db.exists("Customer", name):
		frappe.get_doc({"doctype": "Customer", "name": name, "customer_name": name}).db_insert()
	return name


def _implementation(name, customer, show=1, stakeholder_email=None, stakeholder_contact=None, **values):
	# db_insert skips Implementation.before_save (financial snapshots, chapters), which these
	# tests do not need.
	doc = frappe.get_doc(
		{
			"doctype": "Implementation",
			"name": name,
			"customer": customer,
			"show_on_customer_portal": show,
			**values,
		}
	)
	doc.db_insert()
	if stakeholder_email or stakeholder_contact:
		row = frappe.get_doc(
			{
				"doctype": "Implementation Stakeholder",
				"parent": name,
				"parenttype": "Implementation",
				"parentfield": "stakeholders",
				"idx": 1,
				"email": stakeholder_email or "someone-else@example.com",
				"contact": stakeholder_contact,
				"stakeholder_organisation": "Customer",
				"stakeholder_type": "Sponsor",
			}
		)
		row.db_insert()
	return name


class TestImplementationCockpit(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("User", USER):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": USER,
					"first_name": "IC Customer",
					"user_type": "Website User",
					"send_welcome_email": 0,
				}
			).insert(ignore_permissions=True)
		contact = frappe.get_doc(
			{"doctype": "Contact", "first_name": "IC Customer", "user": USER, "email_ids": [{"email_id": USER, "is_primary": 1}]}
		).insert(ignore_permissions=True)
		cls.contact = contact.name

		own = _customer(PREFIX + "Own Customer")
		other = _customer(PREFIX + "Other Customer")
		cls.by_contact = _implementation(
			PREFIX + "By Contact",
			own,
			stakeholder_contact=contact.name,
			status="Escalated",
			forecast="5 ⛈️ - Kunde zahlt Rechnungen nicht, Kunde hat keine Gedult",
			notes="internal note",
			maturity_level="4 - Go Live Phase. Go Live, first modules in use with real life data",
		)
		cls.by_email = _implementation(PREFIX + "By Email", own, stakeholder_email=USER)
		cls.hidden = _implementation(PREFIX + "Not On Portal", own, show=0, stakeholder_email=USER)
		cls.foreign = _implementation(PREFIX + "Other Customer", other, stakeholder_email="x@example.com")

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_customer_sees_only_own_portal_implementations(self):
		frappe.set_user(USER)
		names = ic._allowed_implementations()
		self.assertIn(self.by_contact, names)
		self.assertIn(self.by_email, names)
		self.assertNotIn(self.hidden, names)
		self.assertNotIn(self.foreign, names)

	def test_scope_groups_by_customer_for_a_customer_user(self):
		frappe.set_user(USER)
		scope = ic.get_scope()
		self.assertFalse(scope["is_internal"])
		self.assertEqual([c["name"] for c in scope["customers"]], [PREFIX + "Own Customer"])
		self.assertEqual(
			{i["name"] for i in scope["customers"][0]["implementations"]}, {self.by_contact, self.by_email}
		)

	def test_customer_cannot_open_another_implementation(self):
		frappe.set_user(USER)
		for name in (self.foreign, self.hidden, "does not exist"):
			with self.subTest(implementation=name), self.assertRaises(frappe.PermissionError):
				ic.get_overview(name)

	def test_overview_hides_internal_fields(self):
		frappe.set_user(USER)
		overview = ic.get_overview(self.by_contact)
		self.assertNotIn("forecast", overview)
		self.assertNotIn("notes", overview)
		self.assertNotIn("Rechnungen", frappe.as_json(overview))
		self.assertEqual(overview["status"], "Active")  # Escalated is internal
		self.assertEqual(overview["phase_number"], 4)
		self.assertEqual(overview["phase"], "Go Live")

	def test_internal_user_sees_all_readable_implementations(self):
		names = ic._allowed_implementations()  # Administrator
		for name in (self.by_contact, self.hidden, self.foreign):
			self.assertIn(name, names)
		self.assertTrue(ic.get_scope()["is_internal"])

	def test_guest_has_no_access(self):
		frappe.set_user("Guest")
		self.assertFalse(ic.check_app_permission())

	def test_phase_label_parsing(self):
		self.assertEqual(ic._phase_label("6 - Support Phase. System in daily use"), "Support")
		self.assertEqual(ic._phase_number("2 - Initial Development Phase. Initial development"), 2)
		self.assertIsNone(ic._phase_label(None))
		self.assertIsNone(ic._phase_number(""))
