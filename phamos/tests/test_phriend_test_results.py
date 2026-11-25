"""Phriend: test results posted to a GitLab issue (#1939).
bench --site <site> run-tests --module phamos.tests.test_phriend_test_results
"""

import json
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phriend import api, setup
from phamos.tests.test_phriend import PNG, response


class PhriendCase(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup.after_migrate()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("phriend_test2")
		self.set_settings(
			enabled=1, allowed_role="System Manager", assign_to=None, default_project=None,
			gitlab_url="https://git.example.com", gitlab_project="phamos/phamos", gitlab_labels="phriend",
		)
		# a token, so GitLab calls are possible (requests are mocked in every test)
		settings = frappe.get_doc("Phriend Settings")
		settings.gitlab_token = "glpat-test"
		settings.save(ignore_permissions=True)
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="phriend_test2")
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")

	def set_settings(self, **values):
		frappe.db.set_single_value("Phriend Settings", values)
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")


@patch("frappe.enqueue")
class TestTestResults(PhriendCase):
	def parse(self, ref):
		return api._parse_gitlab_reference(ref, "https://git.example.com", "phamos/phamos")

	def test_issue_references_in_every_spelling(self, _enqueue):
		self.assertEqual(self.parse("#1862"), ("phamos/phamos", 1862))
		self.assertEqual(self.parse(" 1862 "), ("phamos/phamos", 1862))
		self.assertEqual(self.parse("demo/app#7"), ("demo/app", 7))
		self.assertEqual(self.parse("https://git.example.com/phamos/phamos/-/issues/1862"), ("phamos/phamos", 1862))
		self.assertEqual(self.parse("https://git.example.com/a/b/c/-/work_items/3#note_9"), ("a/b/c", 3))

	def test_links_to_another_gitlab_and_nonsense_are_refused(self, _enqueue):
		with self.assertRaises(frappe.ValidationError):
			self.parse("https://evil.example.org/phamos/phamos/-/issues/1")
		with self.assertRaises(frappe.ValidationError):
			self.parse("not an issue")
		with self.assertRaises(frappe.ValidationError):
			self.parse("")

	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.requests.get")
	def test_result_is_posted_as_a_comment_with_the_screenshot(self, get, post, _enqueue):
		get.return_value = response(json={
			"web_url": "https://git.example.com/phamos/phamos/-/issues/1862",
			"title": "DAP running first", "references": {"full": "phamos/phamos#1862"},
		})
		post.side_effect = [
			response(json={"markdown": "![shot](/uploads/abc/shot.png)"}),  # upload
			response(json={"id": 42}),  # note
		]
		result = api.add_test_evidence(
			gitlab_issue="#1862", result="Failed", title="Stop dialog", comment="Clicked Stop.\nNo issue shown.",
			route="dev-action-panel", page_url="http://site/app/dev-action-panel",
			context=json.dumps({"browser": "Chrome 142"}), screenshot=PNG,
		)
		self.assertEqual(result["web_url"], "https://git.example.com/phamos/phamos/-/issues/1862#note_42")
		self.assertEqual(result["reference"], "phamos/phamos#1862")
		self.assertIn("/projects/phamos%2Fphamos/issues/1862", get.call_args[0][0])
		upload_url, note_url = post.call_args_list[0][0][0], post.call_args_list[1][0][0]
		self.assertTrue(upload_url.endswith("/projects/phamos%2Fphamos/uploads"))
		self.assertTrue(note_url.endswith("/projects/phamos%2Fphamos/issues/1862/notes"))
		body = post.call_args_list[1][1]["data"]["body"]
		self.assertIn("❌ Test failed: Stop dialog", body)
		self.assertIn("No issue shown.", body)
		self.assertIn("![shot](/uploads/abc/shot.png)", body)
		self.assertIn("Chrome 142", body)
		# no ERPNext Issue: a test result is not a problem report
		self.assertFalse(frappe.db.exists("Issue", {"subject": ["like", "%Stop dialog%"]}))
		# the next test result suggests this issue
		target = api.get_test_target()
		self.assertTrue(target["allowed"])
		self.assertEqual(target["target"]["reference"], "https://git.example.com/phamos/phamos/-/issues/1862")

	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.requests.get")
	def test_an_unknown_issue_posts_nothing(self, get, post, _enqueue):
		get.return_value = response(status=404, json={"message": "404 Not found"})
		with self.assertRaises(frappe.ValidationError):
			api.add_test_evidence(gitlab_issue="#999999", result="Passed")
		post.assert_not_called()

	@patch("phamos.phriend.api.requests.put")
	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.requests.get")
	def test_a_status_replaces_the_old_status_label(self, get, post, put, _enqueue):
		get.return_value = response(json={
			"web_url": "https://git.example.com/phamos/phamos/-/issues/1862", "title": "DAP",
			"labels": ["Testing", "Testing on Staging", "P:1", "Discussion"],
		})
		post.return_value = response(json={"id": 5})
		put.return_value = response(json={"labels": ["Ready for Production", "P:1", "Discussion"]})
		result = api.add_test_evidence(gitlab_issue="#1862", result="Passed", title="Stop", status="Ready for Production")
		self.assertEqual(result["status"], "Ready for Production")
		self.assertIsNone(result["status_error"])
		self.assertTrue(put.call_args[0][0].endswith("/projects/phamos%2Fphamos/issues/1862"))
		data = put.call_args[1]["data"]
		self.assertEqual(data["add_labels"], "Ready for Production")
		self.assertEqual(data["remove_labels"], "Testing,Testing on Staging")  # markers stay
		self.assertIn("Status → Ready for Production", post.call_args[1]["data"]["body"])
		self.assertIn("Ready for Production", api.get_test_target()["statuses"])

	@patch("phamos.phriend.api.requests.put")
	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.requests.get")
	def test_no_status_leaves_labels_alone_and_a_failed_status_keeps_the_comment(self, get, post, put, _enqueue):
		get.return_value = response(json={"web_url": "https://git.example.com/phamos/phamos/-/issues/7", "labels": ["Testing"]})
		post.return_value = response(json={"id": 6})
		api.add_test_evidence(gitlab_issue="#7", result="Note")
		put.assert_not_called()
		put.return_value = response(status=403, json={"message": "403 Forbidden"})
		result = api.add_test_evidence(gitlab_issue="#7", result="Passed", status="Ready for Production")
		self.assertIsNone(result["status"])
		self.assertIn("403", result["status_error"])
		self.assertTrue(result["web_url"].endswith("#note_6"))

	def test_unknown_status_labels_are_refused(self, _enqueue):
		with self.assertRaises(frappe.ValidationError):
			api.add_test_evidence(gitlab_issue="#1", result="Passed", status="Done; drop table")

	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.requests.get")
	def test_every_phriend_user_may_post_results_without_issue_rights(self, get, post, _enqueue):
		user = "phriend-tester-noissue@example.com"
		if not frappe.db.exists("User", user):
			frappe.get_doc({
				"doctype": "User", "email": user, "first_name": "No", "last_name": "Issues",
				"user_type": "System User", "send_welcome_email": 0, "roles": [{"role": "Accounts User"}],
			}).insert(ignore_permissions=True)
		self.set_settings(allowed_role=None)
		get.return_value = response(json={"web_url": "https://git.example.com/phamos/phamos/-/issues/3"})
		post.return_value = response(json={"id": 1})
		frappe.set_user(user)
		self.assertFalse(frappe.has_permission("Issue", "write"))
		self.assertTrue(api.get_test_target()["allowed"])
		api.add_test_evidence(gitlab_issue="#3", result="Passed")

	def test_only_phriend_users_post_results(self, _enqueue):
		self.set_settings(allowed_role="Accounts Manager")
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			api.add_test_evidence(gitlab_issue="#1", result="Passed")
		self.assertEqual(api.get_test_target(), {"allowed": False})
