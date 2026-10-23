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


def _project(name, implementation, customer):
	frappe.get_doc(
		{
			"doctype": "Project",
			"name": name,
			"project_name": name,
			"custom_implementation": implementation,
			"customer": customer,
			"status": "Open",
		}
	).db_insert()
	return name


def _timesheet(name, project, customer, start_date, hours, billable, rating=0, activity="Development"):
	frappe.get_doc(
		{
			"doctype": "Timesheet",
			"name": name,
			"customer": customer,
			"parent_project": project,
			"project_name": project,
			"start_date": start_date,
			"end_date": start_date,
			"employee_name": "IC Tester",
			"total_hours": hours,
			"total_billable_hours": billable,
			"custom_rating": rating,
			"docstatus": 0,
		}
	).db_insert()
	frappe.get_doc(
		{
			"doctype": "Timesheet Detail",
			"parent": name,
			"parenttype": "Timesheet",
			"parentfield": "time_logs",
			"idx": 1,
			"activity_type": activity,
			"description": f"Work on {name}",
			"hours": hours,
			"project": project,
		}
	).db_insert()
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

		own_project = _project(PREFIX + "Core Project", cls.by_contact, own)
		other_impl_project = _project(PREFIX + "Webshop Project", cls.by_email, own)
		foreign_project = _project(PREFIX + "Foreign Project", cls.foreign, other)
		cls.ts_march = _timesheet(PREFIX + "TS 1", own_project, own, "2026-03-03", 8, 6)
		cls.ts_may = _timesheet(PREFIX + "TS 2", own_project, own, "2026-05-12", 4, 4)
		cls.ts_rated = _timesheet(PREFIX + "TS 3", own_project, own, "2026-05-20", 2, 0, rating=3)
		cls.ts_other_impl = _timesheet(PREFIX + "TS 4", other_impl_project, own, "2026-05-12", 5, 5)
		cls.ts_foreign = _timesheet(PREFIX + "TS 5", foreign_project, other, "2026-05-12", 7, 7)

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

	def test_timesheets_are_scoped_to_the_implementation(self):
		frappe.set_user(USER)
		result = ic.get_timesheets(self.by_contact, from_date="2026-01-01", to_date="2026-12-31")
		names = {r["name"] for r in result["timesheets"]}
		self.assertEqual(names, {self.ts_march, self.ts_may, self.ts_rated})
		self.assertEqual(result["total"], 3)
		first = next(r for r in result["timesheets"] if r["name"] == self.ts_march)
		self.assertEqual(first["activity_type"], "Development")
		self.assertEqual(first["related_issue"], f"Work on {self.ts_march}")

	def test_timesheets_of_other_customers_are_unreachable(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			ic.get_timesheets(self.foreign)
		# A project of another implementation does not widen the scope.
		result = ic.get_timesheets(self.by_contact, project=PREFIX + "Foreign Project")
		self.assertEqual(result["total"], 0)

	def test_malicious_parameters_do_not_widen_the_result(self):
		frappe.set_user(USER)
		result = ic.get_timesheets(
			self.by_contact,
			project="x' OR '1'='1",
			sort_by="name; DROP TABLE tabTimesheet",
			page_length="5 OFFSET 0 UNION SELECT 1",
			start="-3",
		)
		self.assertEqual(result["total"], 0)
		result = ic.get_timesheets(self.by_contact, sort_by="evil", page_length="1")
		self.assertEqual(len(result["timesheets"]), 1)
		self.assertEqual(result["total"], 3)

	def test_summary_totals_and_empty_periods(self):
		frappe.set_user(USER)
		summary = ic.get_timesheet_summary(self.by_contact, from_date="2026-03-01", to_date="2026-05-31")
		self.assertEqual(summary["hours"], 14)
		self.assertEqual(summary["billable_hours"], 10)
		self.assertEqual(summary["non_billable_hours"], 4)
		self.assertEqual([str(p["start"]) for p in summary["periods"]], ["2026-03-01", "2026-04-01", "2026-05-01"])
		self.assertEqual([p["hours"] for p in summary["periods"]], [8, 0, 6])
		weeks = ic.get_timesheet_summary(self.by_contact, from_date="2026-05-11", to_date="2026-05-24", group_by="week")
		self.assertEqual([str(p["start"]) for p in weeks["periods"]], ["2026-05-11", "2026-05-18"])

	def test_feedback_is_checked_and_given_once(self):
		frappe.set_user(USER)
		with self.assertRaises(frappe.PermissionError):
			ic.set_timesheet_feedback(self.by_contact, self.ts_other_impl, 4, "not mine")
		with self.assertRaises(frappe.ValidationError):
			ic.set_timesheet_feedback(self.by_contact, self.ts_march, 7, "too high")
		with self.assertRaises(frappe.ValidationError):
			ic.set_timesheet_feedback(self.by_contact, self.ts_rated, 4, "second time")

		ic.set_timesheet_feedback(self.by_contact, self.ts_march, 4, "Please check the hours on 3 March")
		values = frappe.db.get_value(
			"Timesheet",
			self.ts_march,
			["custom_rating", "customer_comment", "custom_customer_comment_timestamp", "custom_daily_comment_report_sent"],
			as_dict=True,
		)
		self.assertEqual(values.custom_rating, 4)
		self.assertEqual(values.customer_comment, "Please check the hours on 3 March")
		self.assertIsNotNone(values.custom_customer_comment_timestamp)
		self.assertEqual(values.custom_daily_comment_report_sent, 0)
