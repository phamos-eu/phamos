"""Phriend: a desk report becomes an Issue with a ToDo; a triaged Issue becomes a GitLab issue (phamos/phamos#1850).
bench --site <site> run-tests --module phamos.tests.test_phriend
"""

import base64
import io
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from PIL import Image

from phamos.phriend import api, setup
from phamos.phriend.boot import boot_session
from phamos.www.spa_boot import get_spa_boot

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

	def test_report_without_a_title_is_named_after_the_page(self, _enqueue):
		# every step of the flow can be skipped (#1899): no title, no comment, no screenshot
		issue = self.report(title="", comment="", page_title="User Administrator")
		self.assertEqual(issue.subject, "[Bug] User Administrator")

		issue = self.report(title="  ", page_title=None)
		self.assertEqual(issue.subject, "[Bug] User Administrator")  # from the record

		issue = self.report(title=None, page_title="", ref_doctype=None, ref_docname=None, route="Workspaces/Home")
		self.assertEqual(issue.subject, "[Bug] Workspaces/Home")

	def test_a_long_page_title_still_fits_the_subject(self, _enqueue):
		# a skipped title becomes the page name, which the client sends unchecked (review of !1160)
		issue = self.report(title="", page_title="Very long page " * 30)
		self.assertTrue(issue.subject.startswith("[Bug] Very long page"))
		self.assertLessEqual(len(issue.subject), 140)

	def test_jpeg_screenshot_is_saved_as_jpg(self, _enqueue):
		# the flow sends JPEG when it is smaller than PNG (#1899)
		buffer = io.BytesIO()
		Image.new("RGB", (4, 4), (17, 17, 17)).save(buffer, format="JPEG")
		jpeg = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()

		issue = self.report(screenshot=jpeg)

		self.assertTrue(issue.phriend_screenshot.endswith(f"phriend-{issue.name}.jpg"))
		file_doc = frappe.get_doc("File", {"file_url": issue.phriend_screenshot})
		self.assertEqual(file_doc.get_content()[:3], b"\xff\xd8\xff")  # JPEG magic bytes
		self.assertTrue(file_doc.is_private)

	def test_a_broken_screenshot_costs_the_screenshot_not_the_report(self, _enqueue):
		# an empty canvas (page of 0 x 0 pixels) gives "data:,"; the report must still arrive (#1899)
		for broken in ("data:,", "data:image/png;base64,not-base64!", "data:image/gif;base64,R0lGODlh",
				"data:image/jpeg;base64," + base64.b64encode(b"<svg onload=alert(1)>").decode()):
			with self.subTest(broken=broken[:30]):
				issue = self.report(screenshot=broken)
				self.assertFalse(issue.phriend_screenshot)
				self.assertIn("The screenshot could not be saved", issue.description)
				self.assertFalse(frappe.get_all("File", {"attached_to_name": issue.name}))

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

	def test_cockpits_boot_phriend_like_desk(self, _enqueue):
		# the cockpits load no Desk boot: get_spa_boot carries the flag and the versions (#1900)
		boot = get_spa_boot("/personal-cockpit")
		self.assertEqual(boot.phriend, {"enabled": 1})
		self.assertTrue(boot.versions.get("phamos"))
		self.set_settings(enabled=0)
		self.assertIsNone(get_spa_boot("/personal-cockpit").phriend)

	def test_badge_counts_open_reports_by_record_doctype_or_page(self, _enqueue):
		on_record = self.report()  # about User Administrator
		self.report(ref_docname="Guest")  # another User
		on_page = self.report(ref_doctype=None, ref_docname=None, route="sales-cockpit/leads/follow-ups")
		closed = self.report()
		closed.db_set("status", "Closed")

		self.assertEqual(api.count_open_reports(ref_doctype="User", ref_docname="Administrator"), 1)
		self.assertEqual(api.count_open_reports(ref_doctype="User"), 2)
		self.assertEqual(api.count_open_reports(route="sales-cockpit/leads/follow-ups"), 1)
		self.assertEqual(api.count_open_reports(), 0)
		self.assertTrue(on_record.name and on_page.name)

		self.set_settings(allowed_role="No Such Role For Phriend")
		self.assertEqual(api.count_open_reports(ref_doctype="User"), 0)

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
