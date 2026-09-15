# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for the Issue -> Task conversion flow."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.department_cockpit import CockpitConfig, create_task_from_issue

HR = CockpitConfig(
	label="HR",
	department_field="hr_department",
	project_field="hr_timesheet_project",
	roles=("HR Manager", "HR User"),
)

ISSUE_DETAIL = {
	"name": "ISS-1",
	"subject": "Fix the thing",
	"description": "Some description",
	"priority": "Medium",
	"project": None,
}


def _patched(**overrides):
	"""Common mocks for a call that should reach doc creation."""
	defaults = dict(
		has_permission=MagicMock(),
		_require_department=MagicMock(return_value="Human Resources"),
		get_issue=MagicMock(return_value=dict(ISSUE_DETAIL)),
		_converted_task_for_issue=MagicMock(return_value=None),
		set_task_assignees=MagicMock(),
		_reparent_issue_checklists=MagicMock(),
		get_task=MagicMock(return_value={"name": "TASK-1"}),
	)
	defaults.update(overrides)
	return defaults


class TestCreateTaskFromIssue(FrappeTestCase):
	def test_rejects_when_already_converted(self):
		"""The pre-insert duplicate guard must fire before any Task is created."""
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit._require_department",
				return_value="Human Resources",
			),
			patch(
				"phamos.api.department_cockpit.get_issue",
				return_value=dict(ISSUE_DETAIL),
			),
			patch(
				"phamos.api.department_cockpit._converted_task_for_issue",
				return_value="TASK-EXISTING",
			),
			patch("frappe.get_doc") as get_doc,
		):
			with self.assertRaises(frappe.ValidationError):
				create_task_from_issue(
					HR,
					"ISS-1",
					exp_start_date="2026-01-01",
					exp_end_date="2026-01-05",
					assignees=["user@example.com"],
				)
			get_doc.assert_not_called()

	def test_rejects_missing_dates(self):
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit._require_department",
				return_value="Human Resources",
			),
			patch(
				"phamos.api.department_cockpit.get_issue",
				return_value=dict(ISSUE_DETAIL),
			),
			patch(
				"phamos.api.department_cockpit._converted_task_for_issue",
				return_value=None,
			),
		):
			with self.assertRaises(frappe.ValidationError):
				create_task_from_issue(
					HR,
					"ISS-1",
					exp_start_date="",
					exp_end_date="2026-01-05",
					assignees=["user@example.com"],
				)

	def test_rejects_missing_assignees(self):
		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit._require_department",
				return_value="Human Resources",
			),
			patch(
				"phamos.api.department_cockpit.get_issue",
				return_value=dict(ISSUE_DETAIL),
			),
			patch(
				"phamos.api.department_cockpit._converted_task_for_issue",
				return_value=None,
			),
		):
			with self.assertRaises(frappe.ValidationError):
				create_task_from_issue(
					HR,
					"ISS-1",
					exp_start_date="2026-01-01",
					exp_end_date="2026-01-05",
					assignees=[],
				)

	def test_rejects_concurrent_duplicate_after_insert(self):
		"""A second conversion that wins the insert race must still be rejected
		— and must not touch assignees/checklists/issue status. Frappe rolls
		back the whole request transaction on this throw (see frappe/app.py
		`handle_exception` -> `db.rollback(chain=True)`), so the Task inserted
		just above is not left behind; this test only pins the ordering."""
		task_doc = MagicMock()
		task_doc.name = "TASK-NEW"

		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit._require_department",
				return_value="Human Resources",
			),
			patch(
				"phamos.api.department_cockpit.get_issue",
				return_value=dict(ISSUE_DETAIL),
			),
			patch(
				"phamos.api.department_cockpit._converted_task_for_issue",
				return_value=None,
			),
			patch("frappe.get_doc", return_value=task_doc),
			patch("frappe.get_all", return_value=["TASK-OTHER"]),
			patch("phamos.api.department_cockpit._get_project", return_value=None),
			patch("phamos.api.department_cockpit.set_task_assignees") as set_assignees,
			patch(
				"phamos.api.department_cockpit._reparent_issue_checklists"
			) as reparent,
		):
			with self.assertRaises(frappe.ValidationError):
				create_task_from_issue(
					HR,
					"ISS-1",
					exp_start_date="2026-01-01",
					exp_end_date="2026-01-05",
					assignees=["user@example.com"],
				)
			task_doc.insert.assert_called_once()
			set_assignees.assert_not_called()
			reparent.assert_not_called()

	def test_happy_path_closes_issue_and_reparents_checklists(self):
		task_doc = MagicMock()
		task_doc.name = "TASK-NEW"
		issue_doc = MagicMock()

		def get_doc_side_effect(*args, **kwargs):
			if args and args[0] == "Issue":
				return issue_doc
			return task_doc

		with (
			patch("frappe.has_permission"),
			patch(
				"phamos.api.department_cockpit._require_department",
				return_value="Human Resources",
			),
			patch(
				"phamos.api.department_cockpit.get_issue",
				return_value=dict(ISSUE_DETAIL),
			),
			patch(
				"phamos.api.department_cockpit._converted_task_for_issue",
				return_value=None,
			),
			patch("frappe.get_doc", side_effect=get_doc_side_effect),
			patch("frappe.get_all", return_value=[]),
			patch("phamos.api.department_cockpit._get_project", return_value=None),
			patch("phamos.api.department_cockpit.set_task_assignees") as set_assignees,
			patch(
				"phamos.api.department_cockpit._reparent_issue_checklists"
			) as reparent,
			patch(
				"phamos.api.department_cockpit.get_task",
				return_value={"name": "TASK-NEW"},
			),
		):
			result = create_task_from_issue(
				HR,
				"ISS-1",
				exp_start_date="2026-01-01",
				exp_end_date="2026-01-05",
				assignees=["user@example.com"],
			)

			task_doc.insert.assert_called_once()
			set_assignees.assert_called_once_with(HR, "TASK-NEW", users=["user@example.com"])
			reparent.assert_called_once_with("ISS-1", "TASK-NEW")
			self.assertEqual(issue_doc.status, "Closed")
			issue_doc.save.assert_called_once()
			issue_doc.add_comment.assert_called_once()
			self.assertEqual(result["task"]["name"], "TASK-NEW")
