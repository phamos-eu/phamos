# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for Accounting SPA Monthly Implementation Summary APIs."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.accounting_spa import (
	_mis_delta,
	_serialize_mis_row,
	_user_info_map,
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

	def test_mis_delta_billable_above_total(self):
		delta_hours, delta_ratio = _mis_delta(40, 50)
		self.assertEqual(delta_hours, -10)
		self.assertEqual(delta_ratio, -0.25)

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
			},
			user_info={
				"user@example.com": {
					"full_name": "Example User",
					"user_image": "/files/user.png",
				}
			},
		)
		self.assertEqual(row["delta_hours"], 10)
		self.assertEqual(row["delta_ratio"], 0.25)
		self.assertEqual(row["assignees"], ["user@example.com"])
		self.assertEqual(row["assignee_names"], ["Example User"])
		self.assertEqual(row["assignee_images"], ["/files/user.png"])
		self.assertEqual(len(row["assignees"]), len(row["assignee_names"]))
		self.assertEqual(len(row["assignees"]), len(row["assignee_images"]))
		self.assertEqual(row["desk_url"], "/app/monthly-implementation-summary/MIS-0001")

	def test_serialize_mis_row_handles_empty_and_invalid_assign(self):
		for raw in (None, "", "[]", "{not-json", '{"a": 1}'):
			row = _serialize_mis_row(
				{
					"name": "MIS-EMPTY",
					"total_hours": 0,
					"billable_hours": 0,
					"_assign": raw,
				},
				user_info={},
			)
			self.assertEqual(row["assignees"], [])
			self.assertEqual(row["assignee_names"], [])
			self.assertEqual(row["assignee_images"], [])

	def test_serialize_mis_row_preserves_assignee_order(self):
		row = _serialize_mis_row(
			{
				"name": "MIS-ORDER",
				"total_hours": 10,
				"billable_hours": 5,
				"_assign": '["b@example.com", "a@example.com"]',
			},
			user_info={
				"a@example.com": {"full_name": "A User", "user_image": "/a.png"},
				"b@example.com": {"full_name": "B User", "user_image": "/b.png"},
			},
		)
		self.assertEqual(row["assignees"], ["b@example.com", "a@example.com"])
		self.assertEqual(row["assignee_names"], ["B User", "A User"])
		self.assertEqual(row["assignee_images"], ["/b.png", "/a.png"])

	def test_user_info_map_preserves_requested_users(self):
		with patch(
			"frappe.get_all",
			return_value=[
				frappe._dict(name="a@example.com", full_name="A", user_image="/a.png"),
				frappe._dict(name="b@example.com", full_name=None, user_image=None),
			],
		) as get_all:
			info = _user_info_map(["b@example.com", "a@example.com", "missing@example.com"])
			get_all.assert_called_once()
			self.assertEqual(info["a@example.com"]["full_name"], "A")
			self.assertEqual(info["b@example.com"]["full_name"], "b@example.com")
			self.assertNotIn("missing@example.com", info)

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

	def test_get_monthly_implementation_summaries_batches_user_lookup(self):
		with (
			patch("phamos.api.accounting_spa._require_mis_read"),
			patch(
				"frappe.get_list",
				return_value=[
					{
						"name": "MIS-0002",
						"implementation": "IMPL-2",
						"status": "Closed",
						"year": "2026",
						"month": "February",
						"total_hours": 10,
						"billable_hours": 10,
						"modified": "2026-02-01 09:00:00",
						"_assign": '["one@example.com"]',
					},
					{
						"name": "MIS-0002B",
						"implementation": "IMPL-2B",
						"status": "Draft",
						"year": "2026",
						"month": "March",
						"total_hours": 20,
						"billable_hours": 5,
						"modified": "2026-03-01 09:00:00",
						"_assign": '["two@example.com", "one@example.com"]',
					},
				],
			),
			patch(
				"phamos.api.accounting_spa._user_info_map",
				return_value={
					"one@example.com": {"full_name": "One", "user_image": "/1.png"},
					"two@example.com": {"full_name": "Two", "user_image": "/2.png"},
				},
			) as user_info_map,
		):
			rows = get_monthly_implementation_summaries()
			user_info_map.assert_called_once()
			looked_up = set(user_info_map.call_args[0][0])
			self.assertEqual(looked_up, {"one@example.com", "two@example.com"})
			self.assertEqual(len(rows), 2)
			self.assertEqual(rows[0]["status"], "Closed")
			self.assertEqual(rows[0]["assignee_names"], ["One"])
			self.assertEqual(rows[1]["delta_hours"], 15)
			self.assertEqual(rows[1]["delta_ratio"], 0.75)
			self.assertEqual(rows[1]["assignees"], ["two@example.com", "one@example.com"])
			self.assertEqual(rows[1]["assignee_images"], ["/2.png", "/1.png"])

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
				"phamos.api.accounting_spa._user_info_map",
				return_value={
					"manager@example.com": {
						"full_name": "Account Manager",
						"user_image": "/files/manager.png",
					}
				},
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
				return_value={
					"name": "MIS-0004",
					"assignees": ["new@example.com"],
					"assignee_names": ["New User"],
					"assignee_images": ["/new.png"],
				},
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
			self.assertEqual(result["assignee_names"], ["New User"])
			self.assertEqual(result["assignee_images"], ["/new.png"])

	def test_set_monthly_implementation_summary_assignees_requires_write(self):
		with patch(
			"frappe.has_permission",
			side_effect=frappe.PermissionError("Not permitted"),
		):
			with self.assertRaises(frappe.PermissionError):
				set_monthly_implementation_summary_assignees("MIS-0004", users=["x@example.com"])
