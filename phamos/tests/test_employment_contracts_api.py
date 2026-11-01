# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employment Contracts in the HR cockpit: overview KPIs, saving and access."""

import unittest

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, getdate, nowdate

from phamos.api import employment_contracts as api
from phamos.custom_scripts.custom_python.employee_dashboard import get_employee_dashboard_data
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation


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

	def test_monthly_cost_is_in_company_currency_at_planning_rate(self):
		company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
		foreign = "USD" if company_currency != "USD" else "EUR"
		start = add_days(nowdate(), -10)
		before = {c["currency"]: c["amount"] for c in api.get_overview()["monthly_cost"]}
		self.save(effective_from=start, currency=foreign, conversion_rate=0.5)

		after = {c["currency"]: c["amount"] for c in api.get_overview()["monthly_cost"]}
		self.assertNotIn(foreign, after)
		self.assertAlmostEqual(after[company_currency] - before.get(company_currency, 0), 1250)

	def test_new_contract_takes_employee_company_and_currency(self):
		# A company that is neither the user's default nor in the site's default currency, so
		# neither pre-filled default can pass for the right value.
		user_company = frappe.defaults.get_user_default("Company")
		site_currency = frappe.db.get_default("currency")
		company = next(
			(
				c.name
				for c in frappe.get_all("Company", fields=["name", "default_currency"])
				if c.name != user_company and c.default_currency != site_currency
			),
			None,
		)
		if not company:
			raise unittest.SkipTest("needs a company outside the user's default and the site currency")
		self.company = company
		employee = self.make_employee("Other", "Company")

		contract = self.save(employee=employee, effective_from=add_days(nowdate(), -10), submit=0)
		self.assertEqual(contract["company"], company)
		self.assertEqual(contract["currency"], frappe.get_cached_value("Company", company, "default_currency"))
		self.assertEqual(contract["conversion_rate"], 1)


	# Deleting drafts from the cockpit (#1798)

	def test_draft_can_be_deleted(self):
		draft = self.save(submit=0, effective_from=add_days(nowdate(), 10))
		self.assertTrue(draft["can_delete"])
		api.delete_contract(draft["name"])
		self.assertFalse(frappe.db.exists("Employment Contract", draft["name"]))

	def test_submitted_contract_cannot_be_deleted(self):
		contract = self.save(effective_from=add_days(nowdate(), -10))
		self.assertFalse(contract["can_delete"])
		self.assertRaises(frappe.ValidationError, api.delete_contract, contract["name"])
		self.assertTrue(frappe.db.exists("Employment Contract", contract["name"]))

	def test_hr_user_cannot_delete_a_draft(self):
		draft = self.save(submit=0, effective_from=add_days(nowdate(), 10))
		user = "contract-hr-user@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "HR", "send_welcome_email": 0, "roles": [{"role": "HR User"}]}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		self.assertRaises(frappe.PermissionError, api.delete_contract, draft["name"])
		frappe.set_user("Administrator")
		self.assertTrue(frappe.db.exists("Employment Contract", draft["name"]))


class TestMonthlyTrend(unittest.TestCase):
	"""The 12-month chart on the Contracts overview (#1799), without the database."""

	TODAY = getdate("2026-11-15")

	@staticmethod
	def contract(employee, start, end=None, fte=100, cost=1000, currency="EUR"):
		return frappe._dict(
			employee=employee,
			effective_from=getdate(start),
			valid_until=getdate(end) if end else None,
			fte_percentage=fte,
			weekly_hours=40 * fte / 100,
			base_monthly_gross=cost,
			company_currency=currency,
		)

	def trend(self, submitted, drafts=()):
		months = api.monthly_trend(self.TODAY, submitted, list(drafts), "EUR")
		return {m["month"][:7]: m for m in months}

	def test_twelve_months_from_eight_back_to_three_ahead(self):
		months = api.monthly_trend(self.TODAY, [], [], "EUR")
		self.assertEqual(len(months), 12)
		self.assertEqual(months[0]["month"], "2026-03-01")
		self.assertEqual(months[-1]["month"], "2027-02-01")
		self.assertEqual([m["month"] for m in months if m["is_current"]], ["2026-11-01"])
		self.assertEqual(sum(1 for m in months if m["is_future"]), 3)

	def test_contract_that_starts_changes_and_ends(self):
		trend = self.trend(
			[
				self.contract("A", "2026-05-01", "2026-08-31", fte=50, cost=2000),
				self.contract("A", "2026-09-01", "2026-12-31", fte=100, cost=4000),
				self.contract("B", "2026-04-01", fte=80, cost=3000, currency="USD"),
			]
		)
		self.assertEqual(trend["2026-04"]["fte"], 0.8)
		self.assertEqual(trend["2026-04"]["cost"], 0)  # B's cost is in USD, not the chart's EUR
		self.assertEqual(trend["2026-06"]["fte"], 1.3)
		self.assertEqual(trend["2026-06"]["cost"], 2000)
		self.assertEqual(trend["2026-10"]["cost"], 4000)
		self.assertEqual(trend["2027-01"]["fte"], 0.8)
		self.assertEqual(trend["2027-01"]["cost"], 0)

	def test_future_draft_replaces_the_submitted_contract(self):
		trend = self.trend(
			[self.contract("A", "2026-01-01", fte=50, cost=2000)],
			[self.contract("A", "2027-01-01", fte=100, cost=4000)],
		)
		self.assertEqual(trend["2026-12"]["cost"], 2000)
		self.assertEqual(trend["2026-12"]["estimate_cost"], 0)
		self.assertEqual(trend["2027-01"]["cost"], 0)
		self.assertEqual(trend["2027-01"]["estimate_cost"], 4000)
		self.assertEqual(trend["2027-01"]["estimate_fte"], 1)

	def test_duplicate_drafts_count_once(self):
		draft = self.contract("A", "2026-12-01", cost=4000)
		trend = self.trend([], [draft, draft])
		self.assertEqual(trend["2026-12"]["estimate_cost"], 4000)

	def test_drafts_never_count_for_past_or_current_months(self):
		trend = self.trend([], [self.contract("A", "2026-01-01", cost=4000)])
		self.assertEqual(trend["2026-06"]["estimate_cost"], 0)
		self.assertEqual(trend["2026-11"]["estimate_cost"], 0)
		self.assertEqual(trend["2026-12"]["estimate_cost"], 4000)

	def test_current_month_counts_today_like_the_tiles(self):
		trend = self.trend([self.contract("A", "2026-11-10", cost=1000)])
		self.assertEqual(trend["2026-11"]["cost"], 1000)

	def test_capacity_hours_are_weekly_hours_times_52_over_12(self):
		trend = self.trend(
			[self.contract("A", "2026-01-01", fte=50)],
			[self.contract("B", "2026-12-01", fte=75)],
		)
		self.assertEqual(trend["2026-06"]["capacity_hours"], 86.7)  # 20 h × 52 / 12
		self.assertEqual(trend["2026-12"]["capacity_hours"], 86.7)
		self.assertEqual(trend["2026-12"]["estimate_capacity_hours"], 130)  # 30 h × 52 / 12


class TestImplementationHours(FrappeTestCase):
	"""Hours spent and predicted on Implementations in the contracts chart (#1800)."""

	def setUp(self):
		frappe.set_user("Administrator")
		self.this_month = getdate(nowdate()).replace(day=1)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def key(self, offset):
		return str(add_months(self.this_month, offset))[:7]

	def implementation(self, status="Open", predictions=()):
		doc = frappe.get_doc("Implementation", make_implementation().name)  # insert hooks modify it again
		for key, hours in predictions:
			doc.append("resource_planning_prediction", {"month_and_year": key, "prediction": hours})
		doc.save(ignore_permissions=True)
		frappe.db.set_value("Implementation", doc.name, "status", status)
		return doc.name

	def timesheet(self, project, day, hours):
		frappe.get_doc(
			{
				"doctype": "Timesheet",
				"time_logs": [{"project": project, "from_time": f"{day} 09:00:00", "hours": hours}],
			}
		).insert(ignore_permissions=True)

	def project(self, implementation=None):
		return (
			frappe.get_doc(
				{
					"doctype": "Project",
					"project_name": f"_Test Hours {frappe.generate_hash(length=6)}",
					"status": "Open",
					"custom_implementation": implementation,
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def test_predictions_from_active_implementations_only(self):
		next_month = self.key(1)
		before = api.predicted_hours_by_month([next_month]).get(next_month, 0)
		self.implementation("Open", [(next_month, 30)])
		self.implementation("Escalated", [(next_month, 10), (next_month, 20)])  # two rows: their average
		self.implementation("Completed", [(next_month, 500)])
		self.implementation("Cancelled", [(next_month, 500)])
		self.assertEqual(api.predicted_hours_by_month([next_month])[next_month] - before, 45)

	def test_spent_hours_count_every_implementation_project(self):
		last_month = self.key(-1)
		before = api.spent_hours_by_month(last_month, last_month).get(last_month, 0)
		day = f"{last_month}-10"
		self.timesheet(self.project(self.implementation("Open")), day, 3)
		self.timesheet(self.project(self.implementation("Completed")), day, 2)
		self.timesheet(self.project(), day, 100)  # an internal project, no Implementation
		self.assertEqual(api.spent_hours_by_month(last_month, last_month)[last_month] - before, 5)

	def test_overview_months_carry_spent_or_predicted_hours(self):
		months = api.get_overview()["trend"]["months"]
		for month in months:
			if month["is_future"]:
				self.assertIsNone(month["spent_hours"])
				self.assertIsNotNone(month["predicted_hours"])
			else:
				self.assertIsNotNone(month["spent_hours"])
				self.assertIsNone(month["predicted_hours"])

	def test_hr_manager_sees_totals_without_implementation_access(self):
		next_month = self.key(1)
		self.implementation("Open", [(next_month, 30)])
		user = "contract-hr-manager@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "HRM", "send_welcome_email": 0, "roles": [{"role": "HR Manager"}]}
			).insert(ignore_permissions=True)
		frappe.set_user(user)
		self.assertFalse(frappe.has_permission("Implementation", "read"))
		months = {m["month"][:7]: m for m in api.get_overview()["trend"]["months"]}
		self.assertGreaterEqual(months[next_month]["predicted_hours"], 30)
