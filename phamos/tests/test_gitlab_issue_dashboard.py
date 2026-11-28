# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Lead / Cycle Time cards on the GitLab Issue Dashboard use the exact picked dates,
while the monthly charts still use full months."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.gitlab_integration.page.gitlab_issue_dashboard import gitlab_issue_dashboard as dashboard

PROJECT = "_Test GitLab Dashboard Project"


class TestGitLabIssueDashboardDateRange(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# Closed on 10.11 (lead 9 days, cycle 2 days) and on 20.11 (lead 19 days, cycle 4 days).
		self._closed_issue("Inside range", "2026-11-01", "2026-11-08", "2026-11-10")
		self._closed_issue("Outside range", "2026-11-01", "2026-11-16", "2026-11-20")

	def tearDown(self):
		frappe.db.rollback()

	def _closed_issue(self, title, created_at, cycle_started_at, closed_at):
		name = frappe.get_doc({"doctype": "GitLab Issue", "title": title}).insert(ignore_permissions=True).name
		# set_value skips the Link check, so the test project needs no GitLab Project record.
		frappe.db.set_value(
			"GitLab Issue",
			name,
			{
				"gitlab_project": PROJECT,
				"state": "closed",
				"created_at": f"{created_at} 09:00:00",
				"cycle_time_started_at": f"{cycle_started_at} 09:00:00",
				"closed_at": f"{closed_at} 09:00:00",
			},
			update_modified=False,
		)
		return name

	def test_exact_range_keeps_the_picked_days(self):
		self.assertEqual(
			dashboard._resolve_exact_date_range("2026-11-09", "2026-11-11", None),
			(getdate("2026-11-09"), getdate("2026-11-11")),
		)

	def test_chart_range_still_snaps_to_full_months(self):
		self.assertEqual(
			dashboard._resolve_date_range("2026-11-09", "2026-11-11", None),
			(getdate("2026-11-01"), getdate("2026-11-30")),
		)

	def test_reversed_dates_are_swapped(self):
		self.assertEqual(
			dashboard._resolve_exact_date_range("2026-11-11", "2026-11-09", None),
			(getdate("2026-11-09"), getdate("2026-11-11")),
		)

	def test_cards_count_only_issues_closed_in_the_picked_days(self):
		data = dashboard.get_gitlab_issue_dashboard_data(
			projects=[PROJECT], from_date="2026-11-09", to_date="2026-11-11"
		)

		# With the whole month these would be 14 and 3 (both issues averaged).
		self.assertEqual(data["lead_time"]["filtered"], 9)
		self.assertEqual(data["cycle_time"]["filtered"], 2)
		self.assertEqual((data["kpi_from_date"], data["kpi_to_date"]), ("2026-11-09", "2026-11-11"))
		self.assertEqual((data["from_date"], data["to_date"]), ("2026-11-01", "2026-11-30"))

	def test_whole_month_range_counts_both_issues(self):
		data = dashboard.get_gitlab_issue_dashboard_data(
			projects=[PROJECT], from_date="2026-11-01", to_date="2026-11-30"
		)

		self.assertEqual(data["lead_time"]["filtered"], 14)
		self.assertEqual(data["cycle_time"]["filtered"], 3)
