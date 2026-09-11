# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for Accounting SPA Monthly Implementation Summary APIs."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.accounting_spa import (
	_mis_delta,
	_serialize_mis_row,
	get_accounting_settings,
	get_monthly_implementation_summaries,
	get_monthly_implementation_summary,
	set_monthly_implementation_summary_assignees,
)


class TestAccountingSpaMis(FrappeTestCase):
	def test_mis_delta_with_total(self):
		delta_hours, delta_ratio = _mis_delta(100, 80)
		self.assertEqual(delta_hours, 20)
		self.assertEqual(delta_ratio, 0.2)

	def test_mis_delta_zero_total(self):
		delta_hours, delta_ratio = _mis_delta(0, 0)
		self.assertEqual(delta_hours, 0)
		self.assertIsNone(delta_ratio)

	def test_serialize_mis_row_includes_delta_and_desk_url(self):
		row = _serialize_mis_row(
			{
				"name": "MIS-0001",
				"implementation": "IMPL-1",
				"status": "Open",
				"year": "2026",
				"month": "January",
				"total_hours": 40,
				"billable_hours": 30,
				"modified": "2026-01-15 10:00:00",
				"_assign": '["user@example.com"]',
			}
		)
		self.assertEqual(row["delta_hours"], 10)
		self.assertEqual(row["delta_ratio"], 0.25)
		self.assertEqual(row["assignees"], ["user@example.com"])
		self.assertEqual(row["desk_url"], "/app/monthly-implementation-summary/MIS-0001")

	def test_get_accounting_settings_includes_mis_capability(self):
		with (
			patch("phamos.api.accounting_spa._accounting_settings_permission"),
			patch(
				"phamos.api.department_cockpit.get_settings",
				return_value={"accounting_department": "Accounting"},
			),
			patch("phamos.api.accounting_spa._can_read_mis", return_value=True),
		):
			settings = get_accounting_settings()
			self.assertEqual(settings["can_read_monthly_implementation_summary"], 1)

		with (
			patch("phamos.api.accounting_spa._accounting_settings_permission"),
			patch(
				"phamos.api.department_cockpit.get_settings",
				return_value={"accounting_department": "Accounting"},
			),
			patch("phamos.api.accounting_spa._can_read_mis", return_value=False),
		):
			settings = get_accounting_settings()
			self.assertEqual(settings["can_read_monthly_implementation_summary"], 0)

	def test_get_monthly_implementation_summaries_requires_permission(self):
		with patch(
			"frappe.has_permission",
			side_effect=frappe.PermissionError("Not permitted"),
		):
			with self.assertRaises(frappe.PermissionError):
				get_monthly_implementation_summaries()

	def test_get_monthly_implementation_summaries_serializes_rows(self):
		with (
			patch("phamos.api.accounting_spa._require_mis_read"),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "MIS-0002",
						"implementation": "IMPL-2",
						"status": "Draft",
						"year": "2026",
						"month": "February",
						"total_hours": 10,
						"billable_hours": 10,
						"modified": "2026-02-01 09:00:00",
						"_assign": None,
					}
				],
			),
		):
			rows = get_monthly_implementation_summaries()
			self.assertEqual(len(rows), 1)
			self.assertEqual(rows[0]["name"], "MIS-0002")
			self.assertEqual(rows[0]["delta_hours"], 0)
			self.assertEqual(rows[0]["delta_ratio"], 0)
			self.assertEqual(rows[0]["assignee_names"], [])

	def test_get_monthly_implementation_summary_detail(self):
		doc = MagicMock()
		doc.name = "MIS-0003"
		doc.implementation = "IMPL-3"
		doc.status = "Closed"
		doc.year = "2025"
		doc.month = "December"
		doc.total_hours = 50
		doc.billable_hours = 20
		doc.modified = "2025-12-31 12:00:00"
		doc.check_permission = MagicMock()

		with (
			patch("phamos.api.accounting_spa._require_mis_read"),
			patch("frappe.get_doc", return_value=doc),
			patch(
				"phamos.api.accounting_spa.get_assignments",
				return_value=[{"owner": "manager@example.com"}],
			),
			patch(
				"phamos.api.accounting_spa._user_images",
				return_value=["/files/manager.png"],
			),
			patch(
				"phamos.api.accounting_spa._user_label",
				side_effect=lambda u: "Account Manager" if u == "manager@example.com" else u,
			),
		):
			detail = get_monthly_implementation_summary("MIS-0003")
			doc.check_permission.assert_called_with("read")
			self.assertEqual(detail["name"], "MIS-0003")
			self.assertEqual(detail["delta_hours"], 30)
			self.assertEqual(detail["delta_ratio"], 0.6)
			self.assertEqual(detail["assignees"], ["manager@example.com"])
			self.assertEqual(detail["assignee_names"], ["Account Manager"])
			self.assertEqual(detail["assignee_images"], ["/files/manager.png"])
			self.assertEqual(detail["desk_url"], "/app/monthly-implementation-summary/MIS-0003")

	def test_set_monthly_implementation_summary_assignees(self):
		doc = MagicMock()
		doc.name = "MIS-0004"
		doc.implementation = "IMPL-4"
		doc.month = "March"
		doc.year = "2026"
		doc.check_permission = MagicMock()

		with (
			patch("frappe.has_permission"),
			patch("frappe.get_doc", return_value=doc),
			patch(
				"phamos.api.accounting_spa.get_assignments",
				return_value=[{"owner": "old@example.com"}],
			),
			patch("phamos.api.accounting_spa.remove_assignment") as remove_assignment,
			patch("phamos.api.accounting_spa.add_assignment") as add_assignment,
			patch(
				"phamos.api.accounting_spa.get_monthly_implementation_summary",
				return_value={"name": "MIS-0004", "assignees": ["new@example.com"]},
			) as get_detail,
		):
			result = set_monthly_implementation_summary_assignees(
				"MIS-0004", users=["new@example.com"]
			)
			doc.check_permission.assert_called_with("write")
			remove_assignment.assert_called_once_with(
				"Monthly Implementation Summary", "MIS-0004", "old@example.com"
			)
			add_assignment.assert_called_once()
			self.assertEqual(add_assignment.call_args[0][0]["assign_to"], ["new@example.com"])
			get_detail.assert_called_once_with("MIS-0004")
			self.assertEqual(result["assignees"], ["new@example.com"])
