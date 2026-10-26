# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the GitLab Issue Dashboard date range resolution."""

from datetime import date
from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration.page.gitlab_issue_dashboard.gitlab_issue_dashboard import (
	_resolve_date_range,
)


class TestResolveDateRange(FrappeTestCase):
	def test_mid_month_range_snaps_to_full_months(self):
		self.assertEqual(
			_resolve_date_range("2026-03-15", "2026-05-10", None),
			(date(2026, 3, 1), date(2026, 5, 31)),
		)

	def test_reversed_dates_are_swapped(self):
		self.assertEqual(
			_resolve_date_range("2026-05-10", "2026-03-15", None),
			(date(2026, 3, 1), date(2026, 5, 31)),
		)

	def test_february_end_of_month(self):
		self.assertEqual(_resolve_date_range("2026-02-03", "2026-02-10", None)[1], date(2026, 2, 28))
		self.assertEqual(_resolve_date_range("2028-02-03", "2028-02-10", None)[1], date(2028, 2, 29))

	def test_year_covers_whole_year(self):
		self.assertEqual(_resolve_date_range(None, None, "2025"), (date(2025, 1, 1), date(2025, 12, 31)))

	@patch(
		"phamos.gitlab_integration.page.gitlab_issue_dashboard.gitlab_issue_dashboard.nowdate",
		return_value="2026-10-20",
	)
	def test_default_is_last_six_months(self, _nowdate):
		self.assertEqual(_resolve_date_range(None, None, None), (date(2026, 4, 1), date(2026, 10, 31)))
