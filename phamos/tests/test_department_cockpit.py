# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Unit tests for department cockpit scoping helpers."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.api.department_cockpit import (
	CHECKLIST_LIST_LIMIT,
	ISSUE_LIST_LIMIT,
	CockpitConfig,
	_ensure_issue_in_scope,
	_issue_in_scope,
	_issue_or_filters,
	_require_department,
	_serialize_task_detail,
	create_task,
	get_form_options,
	get_checklists,
	get_issues,
	set_task_assignees,
	update_issue,
	update_task,
	validate_project,
)


HR = CockpitConfig(
	label="HR",
	department_field="human_resources_department",
	project_field="human_resources_timesheet_project",
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


class TestTaskOwner(FrappeTestCase):
	"""Task Owner field on Task, separate from assignment (#1751)."""

	def _update(self, doc, **fields):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit.get_task", return_value={"name": "TASK-1"}),
			patch("frappe.get_doc", return_value=doc),
			patch("phamos.api.department_cockpit.assert_fields_unlocked"),
			patch("phamos.api.department_cockpit.add_assignment") as add_assignment,
			patch("phamos.api.department_cockpit.remove_assignment") as remove_assignment,
		):
			update_task(HR, "TASK-1", **fields)
		add_assignment.assert_not_called()
		remove_assignment.assert_not_called()

	def test_field_is_first_section_without_swallowing_standard_fields(self):
		from phamos.cockpits.setup import IMPLEMENTATION_SECTION, ensure_task_fields

		ensure_task_fields()
		frappe.clear_cache(doctype="Task")
		fieldnames = [df.fieldname for df in frappe.get_meta("Task").fields]
		self.assertEqual(
			fieldnames[:4],
			[IMPLEMENTATION_SECTION, "custom_task_owner", "custom_implementation_specific_end", "subject"],
		)
		owner = frappe.get_meta("Task").get_field("custom_task_owner")
		self.assertEqual((owner.fieldtype, owner.options, owner.reqd), ("Link", "User", 0))
		self.assertFalse(frappe.get_meta("Task").get_field(IMPLEMENTATION_SECTION).collapsible)

	def test_update_task_sets_owner_without_touching_assignment(self):
		doc = MagicMock()
		with patch(
			"frappe.db.get_value",
			return_value=frappe._dict(enabled=1, user_type="System User"),
		):
			self._update(doc, custom_task_owner="owner@example.com")
		doc.set.assert_called_once_with("custom_task_owner", "owner@example.com")
		doc.save.assert_called_once()

	def test_update_task_clears_owner(self):
		doc = MagicMock()
		self._update(doc, custom_task_owner="")
		doc.set.assert_called_once_with("custom_task_owner", None)

	def test_update_task_rejects_disabled_unknown_or_website_user(self):
		for row in (
			frappe._dict(enabled=0, user_type="System User"),
			None,
			frappe._dict(enabled=1, user_type="Website User"),
		):
			doc = MagicMock()
			with patch("frappe.db.get_value", return_value=row):
				with self.assertRaises(frappe.ValidationError):
					self._update(doc, custom_task_owner="gone@example.com")
			doc.save.assert_not_called()

	def test_detail_payload_has_owner_and_name(self):
		doc = frappe._dict(
			name="TASK-1",
			issue=None,
			custom_task_owner="owner@example.com",
			owner="creator@example.com",
			modified_by="creator@example.com",
		)
		with (
			patch("phamos.api.department_cockpit.get_assignments", return_value=[]),
			patch(
				"phamos.api.department_cockpit._user_label",
				side_effect=lambda u: {"owner@example.com": "Olga Owner"}.get(u, u or ""),
			),
		):
			payload = _serialize_task_detail(doc)
		self.assertEqual(payload["custom_task_owner"], "owner@example.com")
		self.assertEqual(payload["custom_task_owner_name"], "Olga Owner")


class TestCreateTask(FrappeTestCase):
	"""create_task behind the "New Task" dialog (#1752)."""

	VALID = dict(
		subject="Prepare offer",
		exp_start_date="2026-11-02",
		exp_end_date="2026-11-03",
		expected_time=1,
		priority="Medium",
		custom_task_owner="owner@example.com",
	)

	def _create(self, task_type_exists=True, **overrides):
		fields = {**self.VALID, **overrides}
		subject = fields.pop("subject")
		doc = MagicMock()
		doc.name = "TASK-NEW"
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("phamos.api.department_cockpit._get_project", return_value="PROJ-HR"),
			patch("phamos.api.department_cockpit.validate_project"),
			patch(
				"frappe.db.get_value",
				return_value=frappe._dict(enabled=1, user_type="System User"),
			),
			patch("frappe.db.exists", return_value=task_type_exists),
			patch("frappe.get_doc", return_value=doc) as get_doc,
			patch("phamos.api.department_cockpit.add_assignment") as add_assignment,
			patch("phamos.api.department_cockpit.get_task", return_value={"name": "TASK-NEW"}),
		):
			create_task(HR, subject, **fields)
		return get_doc.call_args.args[0], doc, add_assignment

	def test_valid_call_stores_all_fields_and_assigns_the_owner(self):
		values, doc, add_assignment = self._create(task_type="Development", description="<p>Details</p>")
		self.assertEqual(
			{k: values[k] for k in ("subject", "exp_start_date", "exp_end_date", "priority", "type")},
			{
				"subject": "Prepare offer",
				"exp_start_date": "2026-11-02",
				"exp_end_date": "2026-11-03",
				"priority": "Medium",
				"type": "Development",
			},
		)
		self.assertEqual(values["expected_time"], 1.0)
		self.assertEqual(values["custom_task_owner"], "owner@example.com")
		self.assertEqual(values["department"], "Human Resources")
		self.assertEqual(doc.description, "<p>Details</p>")
		doc.insert.assert_called_once()
		add_assignment.assert_called_once_with(
			{
				"doctype": "Task",
				"name": "TASK-NEW",
				"assign_to": ["owner@example.com"],
				"description": "Prepare offer",
			}
		)

	def test_project_falls_back_to_the_cockpit_project(self):
		values, _doc, _add = self._create()
		self.assertEqual(values["project"], "PROJ-HR")

	def test_rejects_each_missing_or_invalid_required_field(self):
		cases = {
			"empty subject": dict(subject="  "),
			"no start": dict(exp_start_date=None),
			"no end": dict(exp_end_date=""),
			"end before start": dict(exp_start_date="2026-11-03", exp_end_date="2026-11-02"),
			"estimate 0": dict(expected_time=0),
			"no estimate": dict(expected_time=None),
			"no owner": dict(custom_task_owner=""),
			"no priority": dict(priority=None),
			"unknown priority": dict(priority="Whenever"),
		}
		for label, overrides in cases.items():
			with self.subTest(label):
				with self.assertRaises(frappe.ValidationError):
					self._create(**overrides)

	def test_rejects_an_unknown_task_type(self):
		with self.assertRaises(frappe.ValidationError):
			self._create(task_type_exists=False, task_type="Nope")

	def test_form_options_list_task_priorities_and_types(self):
		with (
			patch("frappe.has_permission"),
			patch("phamos.api.department_cockpit._get_department", return_value="Human Resources"),
			patch("phamos.api.department_cockpit._base_form_options", return_value={"projects": []}),
			patch("phamos.api.department_cockpit._get_project_names", return_value=[]),
			patch("phamos.api.department_cockpit._get_project", return_value=None),
			patch("phamos.api.department_cockpit._role_shortlist_users", return_value=[]),
			patch("frappe.get_all", return_value=["Development", "Support"]),
		):
			options = get_form_options(HR)
		self.assertEqual(options["task_priorities"], ["Low", "Medium", "High", "Urgent"])
		self.assertEqual(options["task_types"], ["Development", "Support"])


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
		self.assertEqual(kwargs["limit"], CHECKLIST_LIST_LIMIT)

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
			result["items"],
			[
				{
					"name": "CHK-1",
					"checklist_owner": "owner@example.com",
					"checklist_owner_name": "Owner Example",
					"checklist_owner_image": "owner.png",
				}
			],
		)
		self.assertFalse(result["truncated"])


class TestGetChecklistsTruncation(FrappeTestCase):
	def _rows(self, count):
		return [
			frappe._dict(name=f"CHK-{i}", checklist_owner=None, modified="2026-01-01 10:00:00")
			for i in range(count)
		]

	def _run(self, row_count):
		meta = MagicMock()
		meta.has_field.return_value = False
		with (
			patch("frappe.has_permission"),
			patch("frappe.get_meta", return_value=meta),
			patch(
				"phamos.api.department_cockpit._department_checklist_rows",
				return_value=self._rows(row_count),
			),
			patch("phamos.api.checklist_inbox._item_counts_map", return_value={}),
			patch("phamos.api.checklist_inbox._item_search_map", return_value={}),
			patch(
				"phamos.api.checklist_inbox._serialize_row",
				side_effect=lambda r, counts=None, item_search=None: {"name": r.name},
			),
			patch("phamos.api.department_cockpit._user_images", return_value=[]),
		):
			return get_checklists(HR)

	def test_not_truncated_under_the_cap(self):
		result = self._run(3)
		self.assertFalse(result["truncated"])
		self.assertEqual(len(result["items"]), 3)

	def test_truncated_when_over_the_cap(self):
		result = self._run(CHECKLIST_LIST_LIMIT + 1)
		self.assertTrue(result["truncated"])
		self.assertEqual(len(result["items"]), CHECKLIST_LIST_LIMIT)
