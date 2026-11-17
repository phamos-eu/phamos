"""Phriend: a desk report becomes an Issue with a ToDo; a triaged Issue becomes a GitLab issue (phamos/phamos#1850).
bench --site <site> run-tests --module phamos.tests.test_phriend
"""

import base64
import json
import io
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase
from PIL import Image

from phamos.phriend import api, setup, shortcut
from phamos.phriend.boot import boot_session, phriend_boot
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

	def test_something_else_is_a_report_type(self, _enqueue):
		# the flow offers "Something else" next to Bug, Improvement and Question (#1900)
		issue = self.report(report_type="Other", title="Hard to say")
		self.assertEqual(issue.phriend_type, "Other")
		self.assertEqual(issue.subject, "[Other] Hard to say")
		options = frappe.get_meta("Issue").get_field("phriend_type").options.split("\n")
		self.assertIn("Other", options)

	def test_improvement_is_a_report_type_and_idea_is_not(self, _enqueue):
		# "Idea" read as "this creates a cockpit Idea"; the type is "Improvement" now (#1924)
		issue = self.report(report_type="Improvement", title="Could be faster")
		self.assertEqual(issue.phriend_type, "Improvement")
		self.assertEqual(issue.subject, "[Improvement] Could be faster")
		options = frappe.get_meta("Issue").get_field("phriend_type").options.split("\n")
		self.assertIn("Improvement", options)
		self.assertNotIn("Idea", options)
		# a tab still running the old flow sends "Idea": it arrives as an Improvement
		self.assertEqual(self.report(report_type="Idea").phriend_type, "Improvement")

	def test_patch_moves_idea_reports_to_improvement(self, _enqueue):
		from phamos.patches.v1_0 import rename_phriend_type_idea_to_improvement

		old = self.report(title="Old wish")
		frappe.db.set_value("Issue", old.name, {"phriend_type": "Idea", "subject": "[Idea] Old wish"})
		bug = self.report(title="Still a bug")

		rename_phriend_type_idea_to_improvement.execute()

		self.assertEqual(frappe.db.get_value("Issue", old.name, ["phriend_type", "subject"]),
			("Improvement", "[Idea] Old wish"))  # the subject stays as it was written
		self.assertEqual(frappe.db.get_value("Issue", bug.name, "phriend_type"), "Bug")

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
		self.assertEqual(bootinfo.phriend["enabled"], 1)
		self.set_settings(allowed_role="No Such Role For Phriend")
		bootinfo = frappe._dict()
		boot_session(bootinfo)
		self.assertNotIn("phriend", bootinfo)

	def test_cockpits_boot_phriend_like_desk(self, _enqueue):
		# the cockpits load no Desk boot: get_spa_boot carries the flag and the versions (#1900)
		boot = get_spa_boot("/personal-cockpit")
		self.assertEqual(boot.phriend["enabled"], 1)
		self.assertTrue(boot.versions.get("phamos"))
		self.set_settings(enabled=0)
		boot = get_spa_boot("/personal-cockpit")
		self.assertIsNone(boot.phriend)
		self.assertEqual(boot.versions, {})  # only Phriend needs them

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

		# not for this user: 0, and no message left in the response for the cockpit to show
		frappe.clear_messages()
		self.set_settings(allowed_role="No Such Role For Phriend")
		self.assertEqual(api.count_open_reports(ref_doctype="User"), 0)
		self.assertFalse(frappe.local.message_log)

		# a filter operator smuggled in as an argument is taken as plain text
		self.set_settings(allowed_role="System Manager")
		self.assertEqual(api.count_open_reports(ref_doctype=["like", "%"]), 0)

	def test_first_step_lists_the_open_reports_about_this_page(self, _enqueue):
		# "Already reported here?" on the first step (PM, 2026-11-15)
		older = self.report(title="Older one")
		newer = self.report(title="Newer one", report_type="Improvement")
		closed = self.report(title="Done already")
		closed.db_set("status", "Closed")
		self.report(title="About another user", ref_docname="Guest")
		frappe.db.set_value("Issue", older.name, "creation", "2026-01-01 10:00:00")

		result = api.get_open_reports(ref_doctype="User", ref_docname="Administrator")

		self.assertEqual(result["count"], 2)
		self.assertEqual([r["name"] for r in result["reports"]], [newer.name, older.name])  # newest first
		first = result["reports"][0]
		self.assertEqual(first["title"], "Newer one")  # without "[Improvement] "
		self.assertEqual(first["type"], "Improvement")
		self.assertTrue(first["when"])

		for i in range(5):
			self.report(title=f"Many {i}")
		many = api.get_open_reports(ref_doctype="User", ref_docname="Administrator")
		self.assertEqual((many["count"], len(many["reports"])), (7, 5))  # all counted, five listed

		nothing = {"count": 0, "capped": False, "reports": []}
		self.assertEqual(api.get_open_reports(), nothing)
		self.set_settings(allowed_role="No Such Role For Phriend")
		self.assertEqual(api.get_open_reports(ref_doctype="User"), nothing)

	def test_open_reports_only_for_records_and_issues_the_user_may_read(self, _enqueue):
		# a report's title says something about its record: don't answer for records one can't read
		self.report(title="About the Administrator user")
		self.set_settings(allowed_role="")
		guest_like = "phriend-no-read@example.com"
		if not frappe.db.exists("User", guest_like):
			frappe.get_doc({"doctype": "User", "email": guest_like, "first_name": "No Read",
				"send_welcome_email": 0}).insert(ignore_permissions=True)
		frappe.set_user(guest_like)
		frappe.clear_messages()
		self.assertEqual(api.get_open_reports(ref_doctype="User", ref_docname="Administrator")["count"], 0)
		self.assertEqual(api.count_open_reports(ref_doctype="User", ref_docname="Administrator"), 0)
		self.assertEqual(api.get_open_reports(ref_doctype="No Such DocType")["count"], 0)
		self.assertFalse(frappe.local.message_log)

	# ---- keyboard shortcut (#1900)

	def test_shortcuts_are_written_one_way_and_risky_ones_are_refused(self, _enqueue):
		self.assertEqual(shortcut.normalize("cmd+p"), "Mod+P")
		self.assertEqual(shortcut.normalize(" shift + command + k "), "Mod+Shift+K")
		self.assertEqual(shortcut.normalize("Ctrl+F5"), "Ctrl+F5")
		self.assertEqual(shortcut.normalize(""), "")
		# the examples the browser side's test (shortcut.test.js) checks too: both sides agree
		with open(frappe.get_app_path("phamos", "public", "js", "phriend", "shortcut_rules.json")) as f:
			examples = json.load(f)["examples"]
		for good in examples["allowed"]:
			with self.subTest(allowed=good):
				self.assertEqual(shortcut.normalize(good), good)
		for bad in examples["refused"] + ["Hyper+P", "Option+L"]:
			with self.subTest(refused=bad), self.assertRaises(frappe.ValidationError):
				shortcut.normalize(bad)

	def test_each_user_can_change_switch_off_or_reset_their_shortcut(self, _enqueue):
		self.addCleanup(frappe.defaults.clear_user_default, shortcut.USER_DEFAULT)
		self.set_settings(shortcut="Mod+P")
		self.assertEqual(phriend_boot()["shortcut"], "Mod+P")

		self.assertEqual(api.set_my_shortcut("cmd+shift+k"), "Mod+Shift+K")
		self.assertEqual(phriend_boot(), {"enabled": 1, "shortcut": "Mod+Shift+K", "default_shortcut": "Mod+P", "has_target": 0})

		self.assertEqual(api.set_my_shortcut("Off"), "")
		self.assertEqual(phriend_boot()["shortcut"], "")

		self.assertEqual(api.set_my_shortcut(""), "Mod+P")  # back to the site's
		with self.assertRaises(frappe.ValidationError):
			api.set_my_shortcut("p")
		self.assertEqual(phriend_boot()["shortcut"], "Mod+P")

		# not for users Phriend isn't for
		self.set_settings(allowed_role="No Such Role For Phriend")
		with self.assertRaises(frappe.PermissionError):
			api.set_my_shortcut("Mod+K")

	def test_existing_sites_get_mod_p_once_and_an_empty_shortcut_stays_off(self, _enqueue):
		self.addCleanup(self.set_settings, shortcut="Mod+P")
		frappe.db.delete("Singles", {"doctype": "Phriend Settings", "field": "shortcut"})
		setup.ensure_default_shortcut()
		self.assertEqual(frappe.db.get_single_value("Phriend Settings", "shortcut"), "Mod+P")
		frappe.db.set_single_value("Phriend Settings", "shortcut", "")
		setup.ensure_default_shortcut()
		self.assertEqual(frappe.db.get_single_value("Phriend Settings", "shortcut") or "", "")

	def test_settings_save_the_shortcut_in_one_spelling(self, _enqueue):
		doc = frappe.get_doc("Phriend Settings")
		doc.shortcut = "command+shift+k"
		doc.save()
		self.assertEqual(doc.shortcut, "Mod+Shift+K")

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


# ---- the report on the cockpit Issue page (#1901)


@patch("frappe.enqueue")
class TestPhriendIssuePage(FrappeTestCase):
	# same set-up as TestPhriend; borrowed, not inherited, so its tests don't run twice
	setUpClass = TestPhriend.setUpClass
	setUp = TestPhriend.setUp
	tearDown = TestPhriend.tearDown
	set_settings = TestPhriend.set_settings
	report = TestPhriend.report

	def test_cockpit_issue_carries_the_report(self, _enqueue):
		from phamos.api import personal_cockpit

		self.set_settings(assign_to="Administrator")
		context = {
			"app": "Personal Cockpit", "viewport": "1440x900 @1x", "browser": "Chrome 156, macOS",
			"versions": {"phamos": "15.140.0"}, "user": "someone@example.com", "secret": "x",
			"recent_errors": [{"type": "error", "message": "boom", "cookie": "sid=1"}],
			"failed_requests": [{"url": "/api/method/x", "status": 500, "message": "Server Error"}],
		}
		issue = self.report(context=json.dumps(context), screenshot=PNG)

		block = personal_cockpit.get_issue(issue.name)["phriend"]

		self.assertEqual(block["type"], "Bug")
		self.assertEqual(block["reported_by"], "Administrator")
		self.assertTrue(block["screenshot"].startswith("/private/files/"))
		# a link on this site, whatever host the browser used
		self.assertEqual(block["page_url"], "/app/user/Administrator")
		self.assertEqual(block["ref_url"], "/app/user/Administrator")
		details = block["details"]
		self.assertEqual(details["browser"], "Chrome 156, macOS")
		self.assertEqual(details["versions"], {"phamos": "15.140.0"})
		# only the known keys of the context and of each entry go out
		self.assertNotIn("user", details)
		self.assertNotIn("secret", details)
		self.assertEqual(details["recent_errors"], [{"type": "error", "message": "boom"}])
		self.assertEqual(details["failed_requests"][0]["status"], "500")

	def test_issue_not_from_phriend_has_no_report(self, _enqueue):
		from phamos.api import department_cockpit as dc

		issue = frappe.get_doc({"doctype": "Issue", "subject": "Plain issue"}).insert()
		self.assertIsNone(dc._serialize_issue_detail(issue)["phriend"])

	def test_list_rows_mark_phriend_reports(self, _enqueue):
		from phamos.api.issue_common import LIST_FIELDS, _serialize_issue_row

		reported = self.report()
		plain = frappe.get_doc({"doctype": "Issue", "subject": "Plain issue"}).insert()
		rows = frappe.get_list("Issue", filters={"name": ("in", [reported.name, plain.name])}, fields=LIST_FIELDS)
		marks = {r.name: _serialize_issue_row(r)["phriend_type"] for r in rows}
		self.assertEqual(marks, {reported.name: "Bug", plain.name: None})

	def test_page_link_is_only_a_web_link(self, _enqueue):
		from phamos.phriend.report import issue_report

		for url in ("javascript:alert(1)", "data:text/html,x", "/app/user"):
			self.assertIsNone(issue_report(self.report(page_url=url))["page_url"], url)
		# another host can't be reached through the link (review of !1164)
		for url in (
			"https://evil.example/login?next=1#top",
			"https://evil.example//evil.example/x",
			"https://evil.example/\\evil.example/x",
			"https://evil.example/\\/evil.example",
			"https://evil.example/\t/evil.example",
			"https://evil.example/\n\\evil.example",
		):
			link = issue_report(self.report(page_url=url))["page_url"]
			self.assertTrue(link.startswith("/") and link[1:2] not in ("/", "\\"), repr(link))
			self.assertNotIn("\\", link)
		self.assertEqual(issue_report(self.report(page_url="https://evil.example/login?next=1#top"))["page_url"],
			"/login?next=1#top")

	def test_versions_are_capped(self, _enqueue):
		from phamos.phriend.report import MAX_VERSIONS, issue_report

		many = {f"app{i}": "1.0" for i in range(MAX_VERSIONS + 10)}
		issue = self.report(context=json.dumps({"versions": many}))
		self.assertEqual(len(issue_report(issue)["details"]["versions"]), MAX_VERSIONS)

	def test_old_reports_and_broken_context_still_show(self, _enqueue):
		from phamos.phriend.report import issue_report

		ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
			"Chrome/156.0.0.0 Safari/537.36")
		old = self.report(context=json.dumps({"user_agent": ua}))
		# the cockpit gets browser and system only, as newer reports store it
		self.assertEqual(issue_report(old)["details"]["browser"], "Chrome 156, macOS")
		frappe.db.set_value("Issue", old.name, "phriend_context", "not json")
		old.reload()
		self.assertEqual(issue_report(old)["details"]["recent_errors"], [])
