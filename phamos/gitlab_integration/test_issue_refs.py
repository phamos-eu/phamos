# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab ticket on a timesheet: the system tells the child from the parent."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import issue_refs
from phamos.phamos.page.dev_action_panel import dev_action_panel as dap
from phamos.tests.test_personal_checkin import _ensure_employee, _ensure_user

USER = "dap-gitlab-ref@example.com"
BASE = "https://git.example.test/grp/proj"


class _RefsSetup(FrappeTestCase):
	"""A GitLab project with a parent ticket #10 and its child #11."""

	def setUp(self):
		patcher = patch("frappe.db.commit")
		patcher.start()
		self.addCleanup(patcher.stop)
		frappe.set_user("Administrator")
		self.erp_project = frappe.get_doc(
			{"doctype": "Project", "project_name": f"Refs {frappe.generate_hash(length=6)}", "status": "Open"}
		).insert(ignore_permissions=True).name
		self.gitlab_project = frappe.get_doc(
			{
				"doctype": "GitLab Project",
				"project_id": frappe.generate_hash(length=10),
				"title": "proj",
				"web_url": BASE,
				"namespace": "grp/proj",
				"frappe_project": self.erp_project,
			}
		).insert(ignore_permissions=True).name
		self.parent = self._issue(10, "Customer ticket")
		self.child = self._issue(11, "Developer task", parent=self.parent)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _issue(self, iid, title, parent=None):
		return frappe.get_doc(
			{
				"doctype": "GitLab Issue",
				"issue_id": str(iid),
				"gitlab_project": self.gitlab_project,
				"title": title,
				"state": "opened",
				"issue_url": f"{BASE}/-/work_items/{iid}",
				"parent_issue": parent,
			}
		).insert(ignore_permissions=True).name


class TestGitlabIssueRefs(_RefsSetup):
	# --- telling child from parent -------------------------------------------------------

	def test_child_url_gives_child_and_its_parent(self):
		self.assertEqual(issue_refs.resolve_reference(f"{BASE}/-/work_items/11"), (self.child, self.parent))

	def test_parent_url_gives_parent_only(self):
		self.assertEqual(issue_refs.resolve_reference(f"{BASE}/-/work_items/10"), (None, self.parent))

	def test_issues_url_form_and_short_reference_work_too(self):
		self.assertEqual(issue_refs.resolve_reference(f"{BASE}/-/issues/11"), (self.child, self.parent))
		self.assertEqual(issue_refs.resolve_reference("grp/proj#11"), (self.child, self.parent))

	def test_picked_issue_name_works(self):
		self.assertEqual(issue_refs.resolve_reference(self.child), (self.child, self.parent))
		self.assertEqual(issue_refs.resolve_reference(self.parent), (None, self.parent))

	def test_url_inside_text_is_found(self):
		text = f"Tested the fix, see {BASE}/-/work_items/11 for details."
		self.assertEqual(issue_refs.find_gitlab_issues_in_text(text), (self.child, self.parent))

	# --- issues not synced yet -----------------------------------------------------------

	def _new_issue_data(self, iid):
		return {"iid": iid, "title": "New task", "state": "opened", "web_url": f"{BASE}/-/work_items/{iid}", "labels": []}

	def test_unsynced_child_is_fetched_with_its_parent(self):
		with (
			patch(
				"phamos.gitlab_integration.gitlab_utils.get_issue_for_project", return_value=self._new_issue_data(12)
			) as get_issue,
			patch(
				"phamos.gitlab_integration.gitlab_utils.get_issue_parent",
				return_value={"iid": "10", "webUrl": f"{BASE}/-/work_items/10"},
			),
		):
			child, parent = issue_refs.resolve_reference(f"{BASE}/-/work_items/12", fetch=True)
		get_issue.assert_called_once()
		self.assertEqual(parent, self.parent)
		self.assertEqual(frappe.db.get_value("GitLab Issue", child, ["issue_id", "parent_issue"]), ("12", self.parent))

	def test_lookups_do_not_fetch_unless_asked(self):
		with patch("phamos.gitlab_integration.gitlab_utils.get_issue_for_project") as get_issue:
			self.assertEqual(issue_refs.find_gitlab_issues_in_text(f"See {BASE}/-/work_items/12"), (None, None))
			preview = issue_refs.preview_reference(f"{BASE}/-/work_items/12")
		get_issue.assert_not_called()
		self.assertFalse(preview["found"])
		self.assertTrue(preview["fetchable"])
		self.assertFalse(frappe.db.exists("GitLab Issue", {"gitlab_project": self.gitlab_project, "issue_id": "12"}))

	def test_url_of_an_unknown_project_links_nothing_and_fetches_nothing(self):
		with patch("phamos.gitlab_integration.gitlab_utils.get_issue_for_project") as get_issue:
			reference = "https://git.example.test/other/repo/-/issues/5"
			self.assertEqual(issue_refs.resolve_reference(reference, fetch=True), (None, None))
		get_issue.assert_not_called()

	def test_gitlab_error_while_fetching_links_nothing(self):
		with patch("phamos.gitlab_integration.gitlab_utils.get_issue_for_project", side_effect=Exception("down")):
			self.assertEqual(issue_refs.resolve_reference(f"{BASE}/-/work_items/99", fetch=True), (None, None))

	def test_failed_parent_lookup_keeps_the_fetched_issue(self):
		with (
			patch(
				"phamos.gitlab_integration.gitlab_utils.get_issue_for_project", return_value=self._new_issue_data(13)
			),
			patch("phamos.gitlab_integration.gitlab_utils.get_issue_parent", side_effect=Exception("graphql down")),
		):
			child, parent = issue_refs.resolve_reference(f"{BASE}/-/work_items/13", fetch=True)
		self.assertIsNone(child)
		self.assertEqual(frappe.db.get_value("GitLab Issue", parent, "issue_id"), "13")

	# --- setting the fields on a Timesheet Record ----------------------------------------

	def test_explicit_ticket_wins_over_text(self):
		doc = frappe._dict(gitlab_issue=None, gitlab_parent_issue=None)
		issue_refs.link_gitlab_issues(doc, reference=self.parent, texts=(f"{BASE}/-/work_items/11",))
		self.assertEqual((doc.gitlab_issue, doc.gitlab_parent_issue), (None, self.parent))

	def test_text_does_not_overwrite_an_issue_timer(self):
		doc = frappe._dict(gitlab_issue=self.child, gitlab_parent_issue=self.parent)
		issue_refs.link_gitlab_issues(doc, texts=(f"{BASE}/-/work_items/10",))
		self.assertEqual((doc.gitlab_issue, doc.gitlab_parent_issue), (self.child, self.parent))

	def test_preview_describes_child_and_parent(self):
		preview = issue_refs.preview_reference(f"{BASE}/-/work_items/11")
		self.assertTrue(preview["found"])
		self.assertEqual(preview["child"]["issue_id"], "11")
		self.assertEqual(preview["parent"]["issue_id"], "10")
		self.assertEqual(preview["child"]["project"], self.erp_project)


class TestDapStopLinksGitlabTicket(_RefsSetup):
	"""A generic project timer, the ticket given on Stop."""

	def setUp(self):
		super().setUp()
		_ensure_user(USER)
		self.employee = _ensure_employee(USER)
		self.activity = "DAP Ref Activity"
		if not frappe.db.exists("Activity Type", self.activity):
			frappe.get_doc({"doctype": "Activity Type", "activity_type": self.activity}).insert(ignore_permissions=True)

	def _stop_project_timer(self, result, **kwargs):
		frappe.set_user(USER)
		started = dap.start_project_timer(self.erp_project, 3600, "Generic work", manual_start_time="2026-05-10 08:00:00")
		dap.stop_timer(started["name"], result, activity_type=self.activity, manual_end_time="2026-05-10 09:00:00", **kwargs)
		frappe.set_user("Administrator")
		return frappe.db.get_value("Timesheet Record", started["name"], ["gitlab_issue", "gitlab_parent_issue"])

	def test_picked_child_ticket_sets_child_and_parent(self):
		self.assertEqual(self._stop_project_timer("Tested", gitlab_issue_ref=self.child), (self.child, self.parent))

	def test_pasted_parent_url_sets_parent_only(self):
		self.assertEqual(
			self._stop_project_timer("Call with customer", gitlab_issue_ref=f"{BASE}/-/work_items/10"), (None, self.parent)
		)

	def test_url_in_result_is_used_like_the_project_action_panel(self):
		self.assertEqual(self._stop_project_timer(f"Reviewed {BASE}/-/issues/11"), (self.child, self.parent))

	def test_break_with_url_in_result_links_the_ticket(self):
		frappe.set_user(USER)
		row = dap.create_break_timesheet(
			"2026-05-10 10:00:00",
			"2026-05-10 10:20:00",
			project=self.erp_project,
			goal="Quick question",
			result=f"Answered on {BASE}/-/work_items/11",
			activity_type=self.activity,
		)
		frappe.set_user("Administrator")
		self.assertEqual(
			frappe.db.get_value("Timesheet Record", row["name"], ["gitlab_issue", "gitlab_parent_issue"]),
			(self.child, self.parent),
		)
