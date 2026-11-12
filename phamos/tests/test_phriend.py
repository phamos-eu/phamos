"""Phriend: a desk report becomes an Issue with a ToDo; a triaged Issue becomes a GitLab issue (phamos/phamos#1850).
bench --site <site> run-tests --module phamos.tests.test_phriend
"""

import base64
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phriend import api, setup
from phamos.phriend.boot import boot_session

# a 1x1 PNG
PNG = "data:image/png;base64," + base64.b64encode(
	bytes.fromhex(
		"89504e470d0a1a0a0000000d4948445200000001000000010806000000"
		"1f15c4890000000d49444154789c6360000002000100e221bc330000000049454e44ae426082"
	)
).decode()


def response(status=200, json=None):
	r = MagicMock()
	r.ok = status < 400
	r.status_code = status
	r.json.return_value = json or {}
	return r


@patch("frappe.enqueue")
class TestPhriend(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		setup.after_migrate()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("phriend_test")
		self.set_settings(enabled=1, allowed_role="System Manager", assign_to=None, default_project=None,
			gitlab_url="https://git.example.com", gitlab_project="phamos/phamos", gitlab_labels="phriend")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="phriend_test")
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")

	def set_settings(self, **values):
		if "gitlab_token" in values and not values["gitlab_token"]:
			# a token saved in the form lives encrypted in __Auth; drop it for this test (rolled back after)
			frappe.db.delete("__Auth", {"doctype": "Phriend Settings", "fieldname": "gitlab_token"})
		frappe.db.set_single_value("Phriend Settings", values)
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")

	def report(self, **kwargs):
		# User "Administrator" always exists; any document works
		args = {"title": "Totals are wrong", "comment": "Line 2 shows 0", "report_type": "Bug",
			"priority": "Urgent", "route": "Form/User/Administrator", "page_url": "http://site/app/user/Administrator",
			"ref_doctype": "User", "ref_docname": "Administrator", "context": '{"recent_errors": []}'}
		args.update(kwargs)
		return frappe.get_doc("Issue", api.create_report(**args)["name"])

	# ---- schema

	def test_fields_sit_in_the_implementation_specific_section_at_the_top(self, _enqueue):
		meta = frappe.get_meta("Issue")
		first = meta.fields[0]
		self.assertEqual((first.fieldname, first.label), (setup.IMPLEMENTATION_SECTION, "Implementation Specific"))
		self.assertEqual(first.depends_on, setup.ONLY_PHRIEND)
		self.assertEqual(meta.fields[1].fieldname, "phriend_reported_by")
		self.assertEqual(frappe.db.get_value("Custom Field", {"dt": "Issue", "fieldname": "phriend_type"}, "module"),
			"Phriend")

	def test_default_settings_are_set_once_and_kept_afterwards(self, _enqueue):
		frappe.db.set_single_value("Phriend Settings", "gitlab_project", "")
		setup.ensure_default_settings()
		self.assertEqual(frappe.db.get_single_value("Phriend Settings", "gitlab_project"), "phamos/phamos")
		frappe.db.set_single_value("Phriend Settings", "gitlab_project", "phamos/other")
		setup.ensure_default_settings()
		self.assertEqual(frappe.db.get_single_value("Phriend Settings", "gitlab_project"), "phamos/other")

	# ---- report -> Issue

	def test_report_becomes_an_issue_with_reporter_page_and_screenshot(self, _enqueue):
		issue = self.report(screenshot=PNG)
		self.assertEqual(issue.subject, "[Bug] Totals are wrong")
		self.assertEqual(issue.status, "Open")
		self.assertEqual(issue.priority, "High")  # Issue Priority has no Urgent
		self.assertEqual(issue.raised_by, frappe.db.get_value("User", "Administrator", "email") or "Administrator")
		self.assertEqual(issue.phriend_reported_by, "Administrator")
		self.assertEqual((issue.phriend_ref_doctype, issue.phriend_ref_docname), ("User", "Administrator"))
		self.assertIn("Line 2 shows 0", issue.description)
		self.assertTrue(issue.phriend_screenshot)
		file = frappe.get_doc("File", {"file_url": issue.phriend_screenshot})
		self.assertEqual((file.attached_to_doctype, file.attached_to_name, file.is_private), ("Issue", issue.name, 1))

	def test_report_is_assigned_to_the_reporter_or_the_configured_user(self, _enqueue):
		issue = self.report()
		self.assertTrue(frappe.db.exists("ToDo", {"reference_type": "Issue", "reference_name": issue.name,
			"allocated_to": "Administrator", "status": "Open"}))

		other = frappe.get_all("User", filters={"name": ["not in", ["Administrator", "Guest"]], "enabled": 1},
			pluck="name", limit=1)
		if not other:
			self.skipTest("needs a second enabled user")
		self.set_settings(assign_to=other[0])
		issue = self.report()
		self.assertTrue(frappe.db.exists("ToDo", {"reference_type": "Issue", "reference_name": issue.name,
			"allocated_to": other[0]}))

	def test_unknown_doctype_and_type_are_dropped(self, _enqueue):
		issue = self.report(ref_doctype="No Such DocType", report_type="Rant", priority="Whenever")
		self.assertFalse(issue.phriend_ref_doctype)
		self.assertFalse(issue.phriend_ref_docname)
		self.assertEqual(issue.phriend_type, "Bug")
		self.assertEqual(issue.priority, "Medium")

	def test_report_on_an_unsaved_form_keeps_the_doctype_and_route(self, _enqueue):
		issue = self.report(ref_doctype="Sales Order", ref_docname="new-sales-order-1",
			route="Form/Sales Order/new-sales-order-1")
		self.assertEqual(issue.phriend_ref_doctype, "Sales Order")
		self.assertFalse(issue.phriend_ref_docname)
		self.assertEqual(issue.phriend_route, "Form/Sales Order/new-sales-order-1")

	def test_report_is_refused_when_disabled_or_without_the_role(self, _enqueue):
		self.set_settings(enabled=0)
		with self.assertRaises(frappe.PermissionError):
			self.report()
		self.set_settings(enabled=1, allowed_role="No Such Role For Phriend")
		with self.assertRaises(frappe.PermissionError):
			self.report()

	def test_boot_shows_phriend_only_to_allowed_users(self, _enqueue):
		bootinfo = frappe._dict()
		boot_session(bootinfo)
		self.assertEqual(bootinfo.phriend, {"enabled": 1})
		self.set_settings(allowed_role="No Such Role For Phriend")
		bootinfo = frappe._dict()
		boot_session(bootinfo)
		self.assertNotIn("phriend", bootinfo)

	# ---- Issue -> GitLab

	@patch("phamos.phriend.api.requests.post")
	def test_gitlab_issue_goes_to_the_configured_project_and_is_linked(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		issue = self.report(screenshot=PNG)
		post.side_effect = [
			response(json={"markdown": "![shot](/uploads/x/shot.png)"}),
			response(json={"web_url": "https://git.example.com/phamos/phamos/-/issues/7", "iid": 7,
				"references": {"full": "phamos/phamos#7"}}),
		]

		result = api.create_gitlab_issue(issue.name, labels="phriend,bug")

		self.assertEqual(result["iid"], 7)
		upload, create = post.call_args_list
		self.assertEqual(upload.args[0], "https://git.example.com/api/v4/projects/phamos%2Fphamos/uploads")
		self.assertEqual(create.args[0], "https://git.example.com/api/v4/projects/phamos%2Fphamos/issues")
		self.assertEqual(create.kwargs["headers"], {"PRIVATE-TOKEN": "glpat-test"})
		payload = create.kwargs["data"]
		self.assertEqual(payload["labels"], "phriend,bug")
		self.assertIn("![shot](/uploads/x/shot.png)", payload["description"])
		self.assertIn("- Reported by:", payload["description"])
		self.assertIn("**User** `Administrator`", payload["description"])
		self.assertEqual(frappe.db.get_value("Issue", issue.name, "gitlab_issue_url"),
			"https://git.example.com/phamos/phamos/-/issues/7")

		with self.assertRaises(frappe.ValidationError):  # only once per Issue
			api.create_gitlab_issue(issue.name)

	@patch("phamos.phriend.api.requests.post")
	@patch("phamos.phriend.api.get_decrypted_password", return_value="glpat-from-gitlab-settings")
	def test_gitlab_token_falls_back_to_gitlab_settings(self, _password, post, _enqueue):
		self.set_settings(gitlab_token=None)
		issue = self.report()
		post.return_value = response(json={"web_url": "https://git.example.com/x", "iid": 1})

		api.create_gitlab_issue(issue.name)

		self.assertEqual(post.call_args.kwargs["headers"], {"PRIVATE-TOKEN": "glpat-from-gitlab-settings"})

	@patch("phamos.phriend.api.requests.post")
	def test_token_without_api_scope_gets_a_clear_message(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-read-only")
		issue = self.report()
		post.return_value = response(status=403, json={"error": "insufficient_scope"})

		with self.assertRaises(frappe.ValidationError) as raised:
			api.create_gitlab_issue(issue.name)

		self.assertIn("api", str(raised.exception))
		self.assertFalse(frappe.db.get_value("Issue", issue.name, "gitlab_issue_url"))
