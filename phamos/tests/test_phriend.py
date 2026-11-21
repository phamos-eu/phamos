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
from phamos.phriend import events as phriend_events
from phamos.phriend import quiet as phriend_quiet
from phamos.phriend import voice as phriend_voice
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
		self.set_settings(enabled=1, allowed_role="System Manager", assign_to=None, default_project=None, quiet_mode=0, one_voice=0, bubbles_per_day=1, events=0,
			warning_role="System Manager", warn_ai_run_failed=1, warn_email_failed=1, warn_gitlab_sync_failed=1,
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
		# the section and the team come from phamos/cockpits/setup.py, which setup.ensure_issue_fields
		# runs first; the section shows on every Issue and starts with the team (#1955); Phriend's fields follow
		# and carry the condition themselves
		self.assertFalse(first.depends_on)
		self.assertEqual(meta.fields[1].fieldname, setup.TEAM_FIELD)
		self.assertEqual(meta.fields[2].fieldname, "phriend_reported_by")
		self.assertEqual(meta.get_field("phriend_reported_by").depends_on, setup.PHRIEND_OR_GITLAB)
		self.assertEqual(meta.get_field("phriend_type").depends_on, setup.ONLY_PHRIEND)
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
		# Administrator may open the Implementation Cockpit, so the report flow links to it (#1671)
		self.assertEqual(
			phriend_boot(),
			{"enabled": 1, "shortcut": "Mod+Shift+K", "default_shortcut": "Mod+P", "has_target": 0, "implementation_cockpit": 1,
				"features": {"reactions": 1, "quiet_mode": 0, "one_voice": 0, "events": 0}, "quiet": None, "can_configure": 1,
				"voice": None},
		)

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

	def test_hands_and_reactions_start_on_and_can_be_switched_off(self, _enqueue):
		# a site that saved Phriend Settings before the switch existed gets it on once (#2009)
		self.addCleanup(self.set_settings, reactions=1)
		frappe.db.delete("Singles", {"doctype": "Phriend Settings", "field": "reactions"})
		setup.ensure_default_features()
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")
		self.assertEqual(phriend_boot()["features"]["reactions"], 1)

		# switched off in the form: Desk and the cockpits get 0, and a migrate keeps it off
		self.set_settings(reactions=0)
		setup.ensure_default_features()
		frappe.clear_document_cache("Phriend Settings", "Phriend Settings")
		self.assertEqual(phriend_boot()["features"]["reactions"], 0)

	def test_leave_me_in_peace_needs_its_switch_and_keeps_to_its_limits(self, _enqueue):
		# #2010: each user's quiet time and warning mute, as user defaults
		for key in (phriend_quiet.QUIET_DEFAULT, phriend_quiet.MUTE_DEFAULT):
			self.addCleanup(frappe.defaults.clear_user_default, key)
		with self.assertRaises(frappe.PermissionError):
			api.set_my_quiet("forever")  # off by default
		self.assertIsNone(phriend_boot()["quiet"])

		self.set_settings(quiet_mode=1)
		now = phriend_quiet.now_ms()
		hour = now + 60 * 60 * 1000
		self.assertEqual(api.set_my_quiet(str(hour))["quiet_until"], hour)
		self.assertEqual(phriend_boot()["quiet"]["quiet_until"], hour)
		self.assertEqual(api.set_my_quiet("forever")["quiet_until"], "forever")
		# "for 1 hour" is counted on the server's clock, and the state carries that clock
		state = api.set_my_quiet(minutes=60)
		self.assertAlmostEqual(state["quiet_until"], state["server_now"] + 60 * 60 * 1000, delta=1000)
		for refused in (now - 1000, now + 26 * 60 * 60 * 1000, "soon"):
			with self.subTest(until=refused), self.assertRaises(frappe.ValidationError):
				api.set_my_quiet(refused)
		self.assertIsNone(api.set_my_quiet("")["quiet_until"])  # back

		# a malformed or non-positive number of minutes is refused, not taken as "come back"
		for refused in ("abc", "0", "-5"):
			with self.subTest(minutes=refused), self.assertRaises(frappe.ValidationError):
				api.set_my_quiet(minutes=refused)

		# a migrate doesn't switch the new feature on (only the ones that start on)
		frappe.db.delete("Singles", {"doctype": "Phriend Settings", "field": "quiet_mode"})
		setup.ensure_default_features()
		self.assertFalse(frappe.db.get_single_value("Phriend Settings", "quiet_mode"))
		self.set_settings(quiet_mode=1)

		muted = api.set_my_warning_mute(90)["warnings_muted_until"]
		self.assertAlmostEqual(muted, now + 90 * 60 * 1000, delta=60 * 1000)
		with self.assertRaises(frappe.ValidationError):
			api.set_my_warning_mute(120)  # 90 minutes at most
		self.assertIsNone(api.set_my_warning_mute(0)["warnings_muted_until"])

		# a time that has passed reads as not quiet
		frappe.defaults.set_user_default(phriend_quiet.QUIET_DEFAULT, str(now - 1))
		self.assertIsNone(phriend_quiet.state()["quiet_until"])

	def test_one_voice_counts_each_users_bubbles_per_day(self, _enqueue):
		# #2011: at most "Bubbles per Day" unprompted bubbles per user and (the browser's) day
		self.addCleanup(frappe.defaults.clear_user_default, phriend_voice.DAY_DEFAULT)
		with self.assertRaises(frappe.PermissionError):
			api.claim_my_bubble("2026-11-21")  # off by default
		self.assertIsNone(phriend_boot()["voice"])

		self.set_settings(one_voice=1, bubbles_per_day=2)
		self.assertEqual(phriend_boot()["voice"], {"day": "", "used": 0, "limit": 2})
		self.assertEqual(api.claim_my_bubble("2026-11-21")["granted"], 1)
		self.assertEqual(api.claim_my_bubble("2026-11-21")["granted"], 1)
		third = api.claim_my_bubble("2026-11-21")
		self.assertEqual((third["granted"], third["used"]), (0, 2))
		self.assertEqual(phriend_boot()["voice"], {"day": "2026-11-21", "used": 2, "limit": 2})
		self.assertEqual(api.claim_my_bubble("2026-11-22")["granted"], 1)  # a new day
		with self.assertRaises(frappe.ValidationError):
			api.claim_my_bubble("tomorrow")

		self.set_settings(bubbles_per_day=0)  # never by itself
		self.assertEqual(api.claim_my_bubble("2026-11-23")["granted"], 0)

		# sites that saved Phriend Settings before the field existed get 1, once
		frappe.db.delete("Singles", {"doctype": "Phriend Settings", "field": ["in", ["bubbles_per_day", "one_voice"]]})
		setup.ensure_default_features()
		def stored(field):
			rows = frappe.db.sql("select value from `tabSingles` where doctype='Phriend Settings' and field=%s", field)
			return rows[0][0] if rows else None

		self.assertEqual(int(stored("bubbles_per_day")), 1)
		self.assertFalse(int(stored("one_voice") or 0))

	@patch("frappe.publish_realtime")
	def test_events_reach_one_users_phriend_only_while_switched_on(self, publish, _enqueue):
		# #2012: off by default, nothing is sent
		self.assertFalse(phriend_events.send("Administrator", "idea_vote", "x"))
		publish.assert_not_called()

		self.set_settings(events=1)
		self.assertTrue(phriend_events.send("Administrator", "idea_vote", "Someone voted"))
		event, payload = publish.call_args.args
		self.assertEqual(event, "phriend_event")
		self.assertEqual(publish.call_args.kwargs["user"], "Administrator")
		self.assertEqual((payload["kind"], payload["level"], payload["gesture"]), ("idea_vote", "reaction", "heart"))

		# failures are red warnings while ticked, notes otherwise; sent at once (a rollback follows)
		phriend_events.send("Administrator", "ai_run_failed", "x", "/app/issue/ISS-1")
		self.assertEqual(publish.call_args.args[1]["level"], "warning")
		self.assertFalse(publish.call_args.kwargs["after_commit"])
		self.set_settings(warn_ai_run_failed=0)
		phriend_events.send("Administrator", "ai_run_failed", "x")
		self.assertEqual(publish.call_args.args[1]["level"], "note")

		# a link only to this site or https; never to Guest, unknown kinds or users without the role
		for bad in ("javascript:alert(1)", "//evil.example/x", "/\\evil.example", "http://plain.example"):
			phriend_events.send("Administrator", "gitlab_issue", "x", bad)
			self.assertEqual(publish.call_args.args[1]["link"], "", bad)
		phriend_events.send("Administrator", "gitlab_issue", "x", "/app/issue/ISS 1")
		self.assertEqual(publish.call_args.args[1]["link"], "/app/issue/ISS 1")
		publish.reset_mock()
		self.assertFalse(phriend_events.send("Guest", "idea_vote"))
		self.assertFalse(phriend_events.send("Administrator", "no_such_kind"))
		self.set_settings(allowed_role="No Such Role For Phriend")
		self.assertFalse(phriend_events.send("Administrator", "idea_vote"))
		publish.assert_not_called()

	@patch("frappe.publish_realtime")
	def test_system_warnings_go_to_the_warning_role_and_the_sync_still_fails(self, publish, _enqueue):
		from phamos.gitlab_integration import gitlab_utils

		self.set_settings(events=1, warning_role="System Manager")
		self.assertIn("Administrator", phriend_events.warning_receivers())
		with patch.object(gitlab_utils, "sync_projects_only", side_effect=RuntimeError("GitLab down")):
			with self.assertRaises(RuntimeError):
				gitlab_utils.sync_gitlab_data()
		users = {c.kwargs["user"] for c in publish.call_args_list if c.args[0] == "phriend_event"}
		self.assertIn("Administrator", users)
		self.assertTrue(all(c.args[1]["kind"] == "gitlab_sync_failed" for c in publish.call_args_list))

	@patch("frappe.publish_realtime")
	def test_quiet_changes_reach_the_users_other_tabs(self, publish, _enqueue):
		self.addCleanup(frappe.defaults.clear_user_default, phriend_quiet.QUIET_DEFAULT)
		self.set_settings(quiet_mode=1)
		api.set_my_quiet("forever")
		event, payload = publish.call_args.args
		self.assertEqual((event, payload["kind"], payload["state"]["quiet_until"]), ("phriend_event", "quiet", "forever"))
		self.assertEqual(publish.call_args.kwargs["user"], "Administrator")

	@patch("frappe.publish_realtime")
	def test_a_test_event_needs_the_switch_and_settings_rights(self, publish, _enqueue):
		with self.assertRaises(frappe.PermissionError):
			api.send_test_event("idea_vote")
		self.set_settings(events=1)
		self.assertTrue(api.send_test_event("gitlab_issue"))
		with self.assertRaises(frappe.ValidationError):
			api.send_test_event("nonsense")

	def test_settings_save_the_shortcut_in_one_spelling(self, _enqueue):
		doc = frappe.get_doc("Phriend Settings")
		doc.shortcut = "command+shift+k"
		doc.save()
		self.assertEqual(doc.shortcut, "Mod+Shift+K")

	# ---- Issue -> GitLab

	def gitlab_project(self, project_id="4242", namespace="phamos/phamos"):
		if not frappe.db.exists("GitLab Project", project_id):
			frappe.get_doc({"doctype": "GitLab Project", "project_id": project_id, "namespace": namespace,
				"web_url": f"https://git.example.com/{namespace}", "title": "phamos"}).insert(ignore_permissions=True)
		return project_id

	def created(self, iid, project_id="4242", **extra):
		"""GitLab's answer to POST /projects/:id/issues."""
		return {"web_url": f"https://git.example.com/phamos/phamos/-/issues/{iid}", "iid": iid, "project_id": int(project_id),
			"references": {"full": f"phamos/phamos#{iid}"}, "title": f"Issue {iid}", "state": "opened",
			"labels": ["phriend", "bug"], "created_at": "2026-11-17T09:30:00.000Z",
			"assignees": [{"name": "Dev One", "username": "dev1"}], **extra}

	@patch("phamos.phriend.api.requests.post")
	def test_gitlab_issue_goes_to_the_configured_project_and_is_linked(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		self.gitlab_project()
		issue = self.report(screenshot=PNG)
		post.side_effect = [
			response(json={"markdown": "![shot](/uploads/x/shot.png)"}),
			response(json=self.created(7)),
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

		# the GitLab Issue record exists at once, linked to the Issue
		self.assertEqual(result["gitlab_issue"], "4242-7")
		record = frappe.get_doc("GitLab Issue", "4242-7")
		self.assertEqual((record.issue, record.issue_id, record.gitlab_project, record.state),
			(issue.name, "7", "4242", "opened"))
		self.assertEqual((record.labels, record.assignee, record.gitlab_username), ("phriend, bug", "Dev One", "dev1"))
		self.assertEqual(str(record.created_at), "2026-11-17 09:30:00")

	@patch("phamos.phriend.api.requests.post")
	def test_an_issue_can_hold_several_gitlab_issues(self, post, _enqueue):
		from phamos.phriend.gitlab_issues import issue_gitlab_issues

		self.set_settings(gitlab_token="glpat-test")
		self.gitlab_project()
		issue = self.report()
		post.side_effect = [response(json=self.created(7)), response(json=self.created(8, state="closed"))]

		api.create_gitlab_issue(issue.name)
		api.create_gitlab_issue(issue.name, title="The second part")

		self.assertEqual(post.call_args.kwargs["data"]["title"], "The second part")
		# the field keeps the first; the records hold all of them
		self.assertTrue(frappe.db.get_value("Issue", issue.name, "gitlab_issue_url").endswith("/issues/7"))
		rows = issue_gitlab_issues(issue.name)
		self.assertEqual([row["reference"] for row in rows], ["phamos/phamos#7", "phamos/phamos#8"])
		self.assertEqual(rows[1]["state"], "closed")
		self.assertEqual(rows[0]["labels"], ["phriend", "bug"])
		self.assertEqual(rows[0]["url"], "https://git.example.com/phamos/phamos/-/issues/7")

	@patch("phamos.phriend.api.requests.post")
	def test_a_record_the_webhook_created_first_gets_the_link(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		self.gitlab_project()
		frappe.get_doc({"doctype": "GitLab Issue", "issue_id": "9", "gitlab_project": "4242", "title": "From the webhook",
			"state": "opened"}).insert(ignore_permissions=True)
		issue = self.report()
		post.return_value = response(json=self.created(9))

		result = api.create_gitlab_issue(issue.name)

		self.assertEqual(result["gitlab_issue"], "4242-9")
		self.assertEqual(frappe.db.count("GitLab Issue", {"gitlab_project": "4242", "issue_id": "9"}), 1)
		self.assertEqual(frappe.db.get_value("GitLab Issue", "4242-9", ["issue", "title"]), (issue.name, "From the webhook"))

	@patch("phamos.phriend.api.requests.post")
	def test_unknown_gitlab_project_keeps_the_url_and_logs(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		issue = self.report()
		post.return_value = response(json=self.created(5, project_id="999999"))
		logs = frappe.db.count("Error Log", {"method": "Phriend: GitLab project not synced"})

		result = api.create_gitlab_issue(issue.name)

		self.assertIsNone(result["gitlab_issue"])
		self.assertTrue(frappe.db.get_value("Issue", issue.name, "gitlab_issue_url").endswith("/issues/5"))
		self.assertFalse(frappe.db.exists("GitLab Issue", {"issue": issue.name}))
		self.assertEqual(frappe.db.count("Error Log", {"method": "Phriend: GitLab project not synced"}), logs + 1)

	@patch("phamos.phriend.api.link_created", side_effect=frappe.ValidationError("broken record"))
	@patch("phamos.phriend.api.requests.post")
	def test_a_failed_link_keeps_the_gitlab_issue_so_no_retry_makes_a_second(self, post, _link, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		issue = self.report()
		post.return_value = response(json=self.created(12))
		logs = frappe.db.count("Error Log", {"method": "Phriend: linking the GitLab issue failed"})

		result = api.create_gitlab_issue(issue.name)

		self.assertIsNone(result["gitlab_issue"])
		self.assertTrue(frappe.db.get_value("Issue", issue.name, "gitlab_issue_url").endswith("/issues/12"))
		self.assertTrue(frappe.db.exists("Comment", {"reference_name": issue.name, "content": ["like", "%GitLab issue created%"]}))
		self.assertEqual(frappe.db.count("Error Log", {"method": "Phriend: linking the GitLab issue failed"}), logs + 1)

	@patch("phamos.phriend.api.requests.post")
	def test_issue_not_from_phriend_sends_its_description(self, post, _enqueue):
		self.set_settings(gitlab_token="glpat-test")
		self.gitlab_project()
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Plain issue",
			"description": "<p>Totals are <b>wrong</b></p>"}).insert(ignore_permissions=True)
		post.return_value = response(json=self.created(11))

		api.create_gitlab_issue(issue.name)

		self.assertEqual(len(post.call_args_list), 1)  # no screenshot upload
		description = post.call_args.kwargs["data"]["description"]
		self.assertIn("Totals are **wrong**", description)
		self.assertNotIn("Reported via Phriend", description)
		self.assertIn(f"From ERPNext Issue [{issue.name}]", description)
		self.assertEqual(frappe.db.get_value("GitLab Issue", "4242-11", "issue"), issue.name)

	def test_patch_links_existing_gitlab_urls(self, _enqueue):
		from phamos.patches.v1_0 import link_gitlab_issues_to_issues

		self.gitlab_project()
		url = "https://git.example.com/phamos/phamos/-/issues/21"
		frappe.get_doc({"doctype": "GitLab Issue", "issue_id": "21", "gitlab_project": "4242",
			"issue_url": url.replace("/issues/", "/work_items/")}).insert(ignore_permissions=True)
		linked = self.report()
		linked.db_set("gitlab_issue_url", url)
		not_synced = self.report()
		not_synced.db_set("gitlab_issue_url", "https://git.example.com/phamos/phamos/-/issues/22")

		link_gitlab_issues_to_issues.execute()

		self.assertEqual(frappe.db.get_value("GitLab Issue", "4242-21", "issue"), linked.name)
		self.assertFalse(frappe.db.exists("GitLab Issue", {"issue": not_synced.name}))

	def test_desk_list_needs_read_permission_on_the_issue(self, _enqueue):
		from phamos.phriend.gitlab_issues import get_issue_gitlab

		self.gitlab_project()
		issue = self.report()
		frappe.get_doc({"doctype": "GitLab Issue", "issue_id": "31", "gitlab_project": "4242", "issue": issue.name,
			"title": "Linked", "issue_url": "https://git.example.com/phamos/phamos/-/issues/31"}).insert(ignore_permissions=True)

		self.assertEqual([row["title"] for row in get_issue_gitlab(issue.name)], ["Linked"])
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			get_issue_gitlab(issue.name)

	def test_issue_connections_count_its_gitlab_issues(self, _enqueue):
		from frappe.desk.notifications import get_open_count

		self.gitlab_project()
		issue = self.report()
		for iid in ("32", "33"):
			frappe.get_doc({"doctype": "GitLab Issue", "issue_id": iid, "gitlab_project": "4242", "issue": issue.name,
				"title": f"Linked {iid}", "issue_url": f"https://git.example.com/phamos/phamos/-/issues/{iid}"}).insert(ignore_permissions=True)

		dashboard = frappe.get_meta("Issue").get_dashboard_data()
		self.assertIn({"label": "GitLab", "items": ["GitLab Issue"]}, dashboard.transactions)
		self.assertIn("Task", [item for group in dashboard.transactions for item in group["items"]])  # ERPNext's stays
		counts = get_open_count("Issue", issue.name)["count"]["external_links_found"]
		self.assertEqual([row["count"] for row in counts if row["doctype"] == "GitLab Issue"], [2])

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

	def test_cockpit_issue_lists_its_gitlab_issues(self, _enqueue):
		from phamos.api import personal_cockpit

		self.set_settings(assign_to="Administrator")
		TestPhriend.gitlab_project(self)
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Plain issue"}).insert(ignore_permissions=True)
		frappe.get_doc({"doctype": "GitLab Issue", "issue_id": "41", "gitlab_project": "4242", "issue": issue.name,
			"title": "Linked", "state": "opened", "labels": "Testing",
			"issue_url": "https://git.example.com/phamos/phamos/-/issues/41"}).insert(ignore_permissions=True)

		detail = personal_cockpit.get_issue(issue.name)

		self.assertIsNone(detail["phriend"])
		self.assertEqual(detail["gitlab_issues"], [{"name": "4242-41", "reference": "phamos/phamos#41", "title": "Linked",
			"state": "opened", "labels": ["Testing"], "url": "https://git.example.com/phamos/phamos/-/issues/41",
			"assignee": ""}])

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
