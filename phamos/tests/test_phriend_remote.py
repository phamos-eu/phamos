"""Phriend on a develop or test system sends its reports to the main system (target system).
bench --site <site> run-tests --module phamos.tests.test_phriend_remote
"""

from unittest.mock import MagicMock, patch

import frappe
import requests
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_url
from frappe.utils.password import set_encrypted_password

from phamos.phriend import api, remote, setup
from phamos.phriend.boot import phriend_boot
from phamos.phriend.report import issue_report
from phamos.tests import test_phriend as base

REMOTE_USER = "phriend-remote@example.com"
TARGET = {"target_url": "https://main.example.com", "target_api_key": "key123", "system_name": "develop"}


def response(status=200, json=None):
	r = base.response(status, json)
	r.text = ""
	return r


def report_args(**kwargs):
	args = {"title": "Totals are wrong", "comment": "Line 2 shows 0", "report_type": "Bug", "priority": "High",
		"route": "Form/User/Administrator", "page_url": "https://develop.example.com/app/user/Administrator",
		"ref_doctype": "User", "ref_docname": "Administrator", "context": '{"site": "develop"}'}
	args.update(kwargs)
	return args


@patch("frappe.desk.form.assign_to.notify_assignment")
@patch("frappe.enqueue")
class TestPhriendRemote(FrappeTestCase):
	setUpClass = base.TestPhriend.setUpClass
	set_settings = base.TestPhriend.set_settings

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("phriend_remote_test")
		self.set_settings(enabled=1, allowed_role="System Manager", assign_to=None, default_project=None,
			target_url=None, target_api_key=None, system_name=None)
		if not frappe.db.exists("User", REMOTE_USER):
			frappe.get_doc({"doctype": "User", "email": REMOTE_USER, "first_name": "Phriend Remote",
				"user_type": "Website User", "send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.get_doc("User", REMOTE_USER).add_roles(setup.REMOTE_ROLE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="phriend_remote_test")
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")

	def set_target(self, **values):
		self.set_settings(**{**TARGET, **values})
		set_encrypted_password("Phriend Settings", "Phriend Settings", "s3cret", "target_api_secret")

	def receive(self, **kwargs):
		args = {"reporter_email": frappe.db.get_value("User", "Administrator", "email"), "reporter_name": "Admin",
			"source_system": "develop", "source_url": "https://develop.example.com/whatever", **report_args()}
		args.update(kwargs)
		frappe.set_user(REMOTE_USER)
		try:
			return frappe.get_doc("Issue", remote.receive_report(**args)["name"])
		finally:
			frappe.set_user("Administrator")

	# ---- sending side

	@patch("phamos.phriend.remote.requests.post")
	def test_with_a_target_the_report_goes_there_and_nothing_is_made_here(self, post, *_):
		self.set_target()
		post.return_value = response(json={"message": {"name": "ISS-2026-00042"}})
		issues, files = frappe.db.count("Issue"), frappe.db.count("File")

		result = api.create_report(**report_args(screenshot=base.PNG))

		self.assertEqual(result, {"name": "ISS-2026-00042", "url": "https://main.example.com/app/issue/ISS-2026-00042"})
		self.assertEqual((frappe.db.count("Issue"), frappe.db.count("File")), (issues, files))
		self.assertEqual(post.call_args.args[0], "https://main.example.com/api/method/phamos.phriend.remote.receive_report")
		self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "token key123:s3cret")
		self.assertIs(post.call_args.kwargs["allow_redirects"], False)
		payload = post.call_args.kwargs["json"]
		self.assertEqual((payload["source_system"], payload["source_url"]), ("develop", get_url().rstrip("/")))
		self.assertEqual(payload["reporter_email"], frappe.db.get_value("User", "Administrator", "email"))
		self.assertEqual((payload["title"], payload["screenshot"], payload["ref_docname"]),
			("Totals are wrong", base.PNG, "Administrator"))

	@patch("phamos.phriend.remote.requests.post")
	def test_system_name_defaults_to_the_site(self, post, *_):
		self.set_target(system_name=None)
		post.return_value = response(json={"message": {"name": "ISS-1"}})

		api.create_report(**report_args())

		self.assertEqual(post.call_args.kwargs["json"]["source_system"], frappe.local.site)

	@patch("phamos.phriend.remote.requests.post")
	def test_target_errors_come_back_as_a_clear_message(self, post, *_):
		self.set_target()
		cases = [
			(response(403, json={"exc_type": "PermissionError"}), "Phriend Remote"),
			(response(417, json={"_server_messages": '["{\\"message\\": \\"Phriend is <b>disabled</b>\\"}"]'}),
				"Phriend is disabled"),
			(requests.ConnectionError("refused"), "can't be reached"),
		]
		for answer, text in cases:
			post.reset_mock(return_value=True, side_effect=True)
			if isinstance(answer, Exception):
				post.side_effect = answer
			else:
				post.return_value = answer
			# a ValidationError, never a PermissionError: the flow would tell the user they may not report
			with self.assertRaises(frappe.ValidationError) as raised:
				api.create_report(**report_args())
			self.assertNotIsInstance(raised.exception, frappe.PermissionError)
			self.assertIn(text, str(raised.exception))

	@patch("phamos.phriend.remote.requests.post")
	def test_a_redirect_is_not_followed_and_names_the_new_address(self, post, *_):
		self.set_target()
		redirect = response(301)
		redirect.headers = {"Location": "https://erp.example.com/api/method/phamos.phriend.remote.receive_report"}
		post.return_value = redirect

		with self.assertRaises(frappe.ValidationError) as raised:
			api.create_report(**report_args())

		self.assertIn("redirects to https://erp.example.com", str(raised.exception))
		self.assertEqual(post.call_count, 1)

	def test_without_key_and_secret_nothing_is_sent(self, *_):
		self.set_settings(target_url="https://main.example.com", target_api_key=None)
		with self.assertRaises(frappe.ValidationError):
			api.create_report(**report_args())

	def test_open_reports_and_boot_with_a_target(self, *_):
		issue = base.TestPhriend.report(self)  # a local report from before the target was set
		self.assertEqual(api.count_open_reports(ref_doctype="User", ref_docname="Administrator"), 1)
		self.assertEqual(phriend_boot()["has_target"], 0)

		self.set_target()

		self.assertEqual(api.count_open_reports(ref_doctype="User", ref_docname="Administrator"), 0)
		self.assertEqual(api.get_open_reports(ref_doctype="User", ref_docname="Administrator")["reports"], [])
		self.assertEqual(phriend_boot()["has_target"], 1)
		self.assertTrue(frappe.db.exists("Issue", issue.name))

	@patch("phamos.phriend.remote.requests.post")
	def test_connection_test_needs_phriend_on_at_the_target(self, post, *_):
		self.set_target()
		post.return_value = response(json={"message": {"enabled": 1}})
		self.assertEqual(remote.test_target_connection(), {"url": "https://main.example.com", "system_name": "develop"})
		self.assertTrue(post.call_args.args[0].endswith("/api/method/phamos.phriend.remote.ping"))

		post.return_value = response(json={"message": {"enabled": 0}})
		with self.assertRaises(frappe.ValidationError):
			remote.test_target_connection()

	def test_target_url_must_be_https_except_locally(self, *_):
		doc = frappe.get_doc("Phriend Settings")
		doc.target_api_key = "key"
		for url in ("http://main.example.com", "https://main.example.com/app", "ftp://main.example.com"):
			doc.target_url = url
			with self.assertRaises(frappe.ValidationError, msg=url):
				doc.validate_target()
		for url, kept in (("https://main.example.com/", "https://main.example.com"),
			("http://erpnext.local:8000", "http://erpnext.local:8000"), ("http://localhost:8000", "http://localhost:8000")):
			doc.target_url = url
			doc.validate_target()
			self.assertEqual(doc.target_url, kept)

	# ---- receiving side

	def test_receive_makes_the_issue_marked_with_its_system(self, *_):
		issue = self.receive(screenshot=base.PNG,
			page_url="https://evil.example/app/user/Administrator?tab=1")

		self.assertEqual((issue.phriend_source_system, issue.phriend_source_url),
			("develop", "https://develop.example.com"))
		self.assertEqual(issue.phriend_reported_by, "Administrator")  # matched by e-mail
		self.assertEqual(issue.raised_by, frappe.db.get_value("User", "Administrator", "email"))
		self.assertEqual(issue.owner, REMOTE_USER)
		# the browser's host is dropped: the page is on the system the report came from
		self.assertEqual(issue.phriend_page_url, "https://develop.example.com/app/user/Administrator?tab=1")
		# a record name there says nothing here: named and linked to there, not linked here
		self.assertEqual((issue.phriend_ref_doctype, issue.phriend_ref_docname), ("User", None))
		self.assertIn('href="https://develop.example.com/app/user/Administrator"', issue.description)
		self.assertIn("on develop", issue.description)
		self.assertTrue(issue.phriend_screenshot)
		self.assertEqual(frappe.db.get_value("ToDo", {"reference_name": issue.name, "status": "Open"}, "allocated_to"),
			"Administrator")

		block = issue_report(issue)
		self.assertEqual(block["source_system"], "develop")
		self.assertEqual(block["page_url"], "https://develop.example.com/app/user/Administrator?tab=1")

	def test_unknown_reporter_keeps_name_and_email(self, *_):
		self.set_settings(assign_to="Administrator")
		issue = self.receive(reporter_email="tester@nowhere.example", reporter_name="Test Er")

		self.assertIsNone(issue.phriend_reported_by)
		self.assertEqual((issue.phriend_reported_by_name, issue.raised_by), ("Test Er", "tester@nowhere.example"))
		self.assertEqual(frappe.db.get_value("ToDo", {"reference_name": issue.name, "status": "Open"}, "allocated_to"),
			"Administrator")

	def test_unknown_reporter_without_assignee_gets_no_todo(self, *_):
		issue = self.receive(reporter_email="tester@nowhere.example", reporter_name="Test Er")
		self.assertFalse(frappe.db.exists("ToDo", {"reference_name": issue.name}))

	def test_receive_is_only_for_phriend_remote(self, *_):
		other = "phriend-no-role@example.com"
		if not frappe.db.exists("User", other):
			frappe.get_doc({"doctype": "User", "email": other, "first_name": "No Role", "user_type": "Website User",
				"send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(other)
		try:
			with self.assertRaises(frappe.PermissionError):
				remote.receive_report(source_url="https://develop.example.com", **report_args())
			with self.assertRaises(frappe.PermissionError):
				remote.ping()
		finally:
			frappe.set_user("Administrator")

	def test_sender_origin_is_only_scheme_host_and_port(self, *_):
		cases = {
			"https://main.example.com@evil.example/app": "https://evil.example",
			"https://user:pw@develop.example.com:8443/x?y=1": "https://develop.example.com:8443",
			"http://[::1]:8000/": "http://[::1]:8000",
			"https://develop.example.com:99999": "",
			"https://develop.example.com:abc": "",
			"javascript:alert(1)": "",
		}
		for url, origin in cases.items():
			self.assertEqual(remote._origin(url), origin, url)

	def test_receive_needs_the_senders_address(self, *_):
		with self.assertRaises(frappe.ValidationError):
			self.receive(source_url="javascript:alert(1)")

	@patch("phamos.phriend.remote.requests.post")
	def test_a_receiving_system_with_a_target_does_not_forward_again(self, post, *_):
		self.set_target()
		issue = self.receive()
		post.assert_not_called()
		self.assertEqual(issue.phriend_source_system, "develop")

	def test_remote_role_exists(self, *_):
		self.assertTrue(frappe.db.exists("Role", setup.REMOTE_ROLE))
