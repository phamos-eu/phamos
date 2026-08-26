# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for department cockpit scoping helpers."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.department_cockpit import (
	CockpitConfig,
	_ensure_issue_in_scope,
	_issue_in_scope,
	_issue_or_filters,
	_require_department,
	validate_project,
)


HR = CockpitConfig(
	label="HR",
	department_field="hr_department",
	project_field="hr_timesheet_project",
	roles=("HR Manager", "HR User"),
)


class TestDepartmentCockpitScope(FrappeTestCase):
	def test_require_department_throws_when_unset(self):
		with patch("phamos.api.department_cockpit._get_department", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				_require_department(HR)

	def test_require_department_returns_configured_value(self):
		with patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"):
			self.assertEqual(_require_department(HR), "Human Resources")

	def test_issue_in_scope_via_custom_department(self):
		doc = MagicMock()
		doc.custom_department = "Human Resources"
		doc.project = None
		with patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"):
			self.assertTrue(_issue_in_scope(HR, doc))

	def test_issue_in_scope_via_project_department(self):
		doc = MagicMock()
		doc.custom_department = None
		doc.project = "PROJ-HR"
		with (
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("frappe.db.get_value", return_value="Human Resources"),
		):
			self.assertTrue(_issue_in_scope(HR, doc))

	def test_issue_out_of_scope(self):
		doc = MagicMock()
		doc.custom_department = "Sales"
		doc.project = None
		with patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"):
			self.assertFalse(_issue_in_scope(HR, doc))
			with self.assertRaises(frappe.ValidationError):
				_ensure_issue_in_scope(HR, doc)

	def test_validate_project_rejects_foreign_department(self):
		with (
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("frappe.db.get_value", return_value="Sales"),
		):
			with self.assertRaises(frappe.ValidationError):
				validate_project(HR, "PROJ-SALES")

	def test_validate_project_accepts_matching_department(self):
		with (
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("frappe.db.get_value", return_value="Human Resources"),
		):
			validate_project(HR, "PROJ-HR")

	def test_issue_or_filters_empty_without_department(self):
		with patch("phamos.api.department_cockpit._get_department", return_value=None):
			self.assertEqual(_issue_or_filters(HR), [])

	def test_issue_or_filters_includes_custom_department_when_field_exists(self):
		meta = MagicMock()
		meta.has_field.return_value = True
		with (
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("phamos.api.department_cockpit._get_project_names", return_value=["P1"]),
			patch("frappe.get_meta", return_value=meta),
		):
			filters = _issue_or_filters(HR)
			self.assertIn(["project", "in", ["P1"]], filters)
			self.assertIn(["custom_department", "=", "Human Resources"], filters)
