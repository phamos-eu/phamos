# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for department cockpit scoping helpers."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.department_cockpit import (
	ISSUE_LIST_LIMIT,
	CockpitConfig,
	_ensure_issue_in_scope,
	_issue_in_scope,
	_issue_or_filters,
	_require_department,
	get_checklists,
	get_issues,
	set_task_assignees,
	update_issue,
	update_task,
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

	def test_update_issue_rejects_unknown_fields(self):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit.get_issue", return_value={"name": "ISS-1"}),
			patch("frappe.get_doc") as get_doc,
		):
			doc = MagicMock()
			get_doc.return_value = doc
			with self.assertRaises(frappe.ValidationError):
				update_issue(HR, "ISS-1", custom_field="nope")
			doc.save.assert_not_called()

	def test_update_issue_rejects_out_of_scope(self):
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit.get_issue",
				side_effect=frappe.ValidationError("out of scope"),
			),
		):
			with self.assertRaises(frappe.ValidationError):
				update_issue(HR, "ISS-1", subject="Updated")

	def test_update_task_rejects_unknown_fields(self):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit.get_task", return_value={"name": "TASK-1"}),
			patch("frappe.get_doc") as get_doc,
		):
			doc = MagicMock()
			get_doc.return_value = doc
			with self.assertRaises(frappe.ValidationError):
				update_task(HR, "TASK-1", is_group=1)
			doc.save.assert_not_called()

	def test_update_task_rejects_out_of_scope(self):
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit.get_task",
				side_effect=frappe.ValidationError("out of scope"),
			),
		):
			with self.assertRaises(frappe.ValidationError):
				update_task(HR, "TASK-1", subject="Updated")


class TestGetIssuesTruncation(FrappeTestCase):
	def _rows(self, count):
		return [frappe._dict(name=f"ISS-{i}") for i in range(count)]

	def _run(self, row_count):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit._require_department"),
			patch(
				"phamos.api.department_cockpit._issue_or_filters",
				return_value=[["priority", "!=", ""]],
			),
			patch("frappe.get_list", return_value=self._rows(row_count)),
			patch(
				"phamos.api.department_cockpit.enrich_issue_rows_for_search",
				side_effect=lambda rows: [dict(r) for r in rows],
			),
			patch("phamos.api.department_cockpit._attach_converted_tasks"),
		):
			return get_issues(HR)

	def test_not_truncated_under_the_cap(self):
		result = self._run(3)
		self.assertFalse(result["truncated"])
		self.assertEqual(len(result["items"]), 3)

	def test_truncated_when_over_the_cap(self):
		result = self._run(ISSUE_LIST_LIMIT + 1)
		self.assertTrue(result["truncated"])
		self.assertEqual(len(result["items"]), ISSUE_LIST_LIMIT)

	def test_empty_or_filters_returns_empty_without_querying(self):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit._require_department"),
			patch("phamos.api.department_cockpit._issue_or_filters", return_value=[]),
			patch("frappe.get_list") as get_list,
		):
			result = get_issues(HR)
		self.assertEqual(result, {"items": [], "truncated": False})
		get_list.assert_not_called()


class TestSetTaskAssignees(FrappeTestCase):
	def test_adds_and_removes_to_match_desired_set(self):
		task_doc = MagicMock()
		task_doc.subject = "Do the thing"
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit.get_task",
				return_value={"name": "TASK-1", "subject": "Do the thing"},
			),
			patch("frappe.get_doc", return_value=task_doc),
			patch(
				"phamos.api.department_cockpit.get_assignments",
				return_value=[{"owner": "a@example.com"}, {"owner": "b@example.com"}],
			),
			patch("phamos.api.department_cockpit.remove_assignment") as remove_assignment,
			patch("phamos.api.department_cockpit.add_assignment") as add_assignment,
		):
			set_task_assignees(HR, "TASK-1", users=["b@example.com", "c@example.com"])

		remove_assignment.assert_called_once_with("Task", "TASK-1", "a@example.com")
		add_assignment.assert_called_once_with(
			{
				"doctype": "Task",
				"name": "TASK-1",
				"assign_to": ["c@example.com"],
				"description": "Do the thing",
			}
		)

	def test_noop_when_assignees_already_match(self):
		task_doc = MagicMock()
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit.get_task",
				return_value={"name": "TASK-1", "subject": "X"},
			),
			patch("frappe.get_doc", return_value=task_doc),
			patch(
				"phamos.api.department_cockpit.get_assignments",
				return_value=[{"owner": "a@example.com"}],
			),
			patch("phamos.api.department_cockpit.remove_assignment") as remove_assignment,
			patch("phamos.api.department_cockpit.add_assignment") as add_assignment,
		):
			set_task_assignees(HR, "TASK-1", users=["a@example.com"])

		remove_assignment.assert_not_called()
		add_assignment.assert_not_called()


class TestGetChecklists(FrappeTestCase):
	def test_default_filters_out_completed(self):
		meta = MagicMock()
		meta.has_field.return_value = False
		with (
			patch("frappe.has_permission"),
			patch("frappe.get_meta", return_value=meta),
			patch(
				"phamos.api.department_cockpit._department_checklist_rows", return_value=[]
			) as rows_fn,
		):
			get_checklists(HR)

		args, kwargs = rows_fn.call_args
		self.assertEqual(args[2], {"status": ("!=", "Completed")})
		self.assertEqual(kwargs["limit"], 200)

	def test_include_completed_drops_status_filter(self):
		meta = MagicMock()
		meta.has_field.return_value = False
		with (
			patch("frappe.has_permission"),
			patch("frappe.get_meta", return_value=meta),
			patch(
				"phamos.api.department_cockpit._department_checklist_rows", return_value=[]
			) as rows_fn,
		):
			get_checklists(HR, include_completed=1)

		args, _ = rows_fn.call_args
		self.assertEqual(args[2], {})

	def test_attaches_checklist_owner_name_and_image(self):
		meta = MagicMock()
		meta.has_field.return_value = False
		row = frappe._dict(
			name="CHK-1", checklist_owner="owner@example.com", modified="2026-01-01 10:00:00"
		)
		with (
			patch("frappe.has_permission"),
			patch("frappe.get_meta", return_value=meta),
			patch(
				"phamos.api.department_cockpit._department_checklist_rows", return_value=[row]
			),
			patch("phamos.api.checklist_inbox._item_counts_map", return_value={"CHK-1": (1, 2)}),
			patch("phamos.api.checklist_inbox._item_search_map", return_value={"CHK-1": ""}),
			patch(
				"phamos.api.checklist_inbox._serialize_row",
				side_effect=lambda r, counts=None, item_search=None: {
					"name": r.name,
					"checklist_owner": r.checklist_owner,
				},
			),
			patch(
				"phamos.api.department_cockpit._user_images", return_value=["owner.png"]
			),
			patch(
				"phamos.api.department_cockpit._user_label", return_value="Owner Example"
			),
		):
			result = get_checklists(HR)

		self.assertEqual(
			result,
			[
				{
					"name": "CHK-1",
					"checklist_owner": "owner@example.com",
					"checklist_owner_name": "Owner Example",
					"checklist_owner_image": "owner.png",
				}
			],
		)
