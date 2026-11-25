# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""phamos Issue Assistant, part one (#2111): setup, intake, assignment, the AI gate and the brief."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.ai_agents import runner
from phamos.ai_agents.agents import issue as assistant
from phamos.setup import issue_assistant as setup

CUSTOMER = "Issue Assistant Test Customer"
DESK_USER = "issue-assistant-desk@example.com"
WEBSITE_USER = "issue-assistant-web@example.com"


def make_user(email, user_type):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"user_type": user_type,
				"send_welcome_email": 0,
				"roles": [{"role": "Support Team"}] if user_type == "System User" else [],
			}
		).insert(ignore_permissions=True)
	return email


class IssueAssistantTestCase(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		# an assignment mail is sent at once in tests and commits the transaction
		patch("frappe.desk.form.assign_to.notify_assignment").start()
		patch("phamos.ai_agents.runner.frappe.publish_realtime").start()
		setup.after_migrate()
		self.settings = frappe.get_single(setup.SETTINGS)
		self.settings.enabled = 1
		self.settings.scope_projects = []
		self.settings.scope_issue_types = []
		self.settings.save(ignore_permissions=True)
		self.assistant = self.settings.assistant_user
		make_user(DESK_USER, "System User")
		make_user(WEBSITE_USER, "Website User")
		if not frappe.db.exists("Customer", CUSTOMER):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": CUSTOMER,
				 "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				 "territory": frappe.db.get_value("Territory", {"is_group": 0})}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 0)

	def tearDown(self):
		patch.stopall()
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def issue(self, **values):
		with patch("phamos.ai_agents.runner.enqueue_run") as enqueue:
			doc = frappe.get_doc({"doctype": "Issue", "subject": "Assistant test", **values}).insert(
				ignore_permissions=True
			)
		self.enqueued = enqueue
		return doc

	def run_assistant(self, doc):
		run = runner.run_now("Issue", doc.name, trigger="Insert")
		self.assertEqual(run.status, "Completed", run.error)
		return run

	def assignees(self, doc):
		return set(
			frappe.get_all(
				"ToDo",
				filters={"reference_type": "Issue", "reference_name": doc.name, "status": "Open"},
				pluck="allocated_to",
			)
		)


class TestSetup(IssueAssistantTestCase):
	def test_setup_runs_twice_without_duplicates(self):
		setup.after_migrate()
		self.assertEqual(frappe.db.count("AI Agent", {"applies_to_doctype": "Issue"}), 1)
		self.assertEqual(frappe.db.count("AI Skill", {"agent": setup.ASSISTANT_NAME, "handler": "check_gate"}), 1)
		self.assertTrue(frappe.get_meta("Customer").has_field(setup.AI_ALLOWED_FIELD))
		self.assertTrue(frappe.db.exists("User", self.assistant))

	def test_role_cannot_delete_issues(self):
		doc = self.issue(raised_by=DESK_USER)
		self.assertTrue(frappe.has_permission("Issue", "write", doc=doc, user=self.assistant))
		self.assertFalse(frappe.has_permission("Issue", "delete", doc=doc, user=self.assistant))


class TestIntake(IssueAssistantTestCase):
	def test_new_issue_is_queued_only_when_enabled_and_in_scope(self):
		self.issue(raised_by=DESK_USER)
		self.enqueued.assert_called_once()

		self.settings.enabled = 0
		self.settings.save(ignore_permissions=True)
		self.issue(raised_by=DESK_USER)
		self.enqueued.assert_not_called()

		self.settings.enabled = 1
		self.settings.append("scope_issue_types", {"issue_type": self.issue_type()})
		self.settings.save(ignore_permissions=True)
		self.issue(raised_by=DESK_USER)
		self.enqueued.assert_not_called()
		self.issue(raised_by=DESK_USER, issue_type=self.issue_type())
		self.enqueued.assert_called_once()

	def issue_type(self):
		if not frappe.db.exists("Issue Type", "Assistant Test Type"):
			frappe.get_doc({"doctype": "Issue Type", "__newname": "Assistant Test Type"}).insert(ignore_permissions=True)
		return "Assistant Test Type"

	def test_assistant_and_desk_reporter_are_assigned(self):
		doc = self.issue(raised_by=DESK_USER)
		self.run_assistant(doc)
		self.assertEqual(self.assignees(doc), {self.assistant, DESK_USER})

	def test_website_user_reporter_is_not_assigned(self):
		doc = self.issue(raised_by=WEBSITE_USER)
		self.run_assistant(doc)
		self.assertEqual(self.assignees(doc), {self.assistant})

	def test_brief_is_kept_on_the_run(self):
		doc = self.issue(raised_by=DESK_USER)
		run = self.run_assistant(doc)
		self.assertIn(doc.name, run.summary)
		self.assertIn(DESK_USER, run.summary)


class TestGate(IssueAssistantTestCase):
	def test_sensitive_page_never_goes(self):
		doc = self.issue(raised_by=DESK_USER, phriend_ref_doctype="Employee")
		gate = assistant.model_allowed(doc)
		self.assertEqual((gate["allowed"], gate["reason"]), (False, assistant.SENSITIVE_PAGE))

	def test_customer_needs_the_switch(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.CUSTOMER_NOT_ALLOWED)
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 1)
		gate = assistant.model_allowed(doc)
		self.assertEqual((gate["allowed"], gate["reason"]), (True, assistant.CUSTOMER_ALLOWED))

	def test_internal_desk_user_goes(self):
		# a Phriend report is inserted in the reporter's session, so they are its owner
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(DESK_USER)
		doc = self.issue(raised_by=DESK_USER, phriend_reported_by=DESK_USER, phriend_type="Bug")
		frappe.set_user("Administrator")
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.INTERNAL)

	def test_reporter_field_sent_by_the_caller_is_not_trusted(self):
		doc = self.issue(raised_by=DESK_USER, phriend_reported_by=DESK_USER, phriend_type="Bug")
		self.assertEqual(doc.owner, "Administrator")
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.UNKNOWN_SENDER)

	def test_issue_created_in_desk_by_staff_goes(self):
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(DESK_USER)
		doc = self.issue(raised_by=DESK_USER)
		frappe.set_user("Administrator")
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.INTERNAL)

	def test_staff_address_in_an_email_is_not_internal(self):
		# an e-mail Issue is inserted by the system; its From header could be forged
		doc = self.issue(raised_by=DESK_USER)
		self.assertEqual(doc.owner, "Administrator")
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.UNKNOWN_SENDER)

	def test_forwarded_report_is_not_internal(self):
		doc = self.issue(raised_by=DESK_USER, phriend_reported_by=DESK_USER, phriend_source_system="Other ERPNext")
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.UNKNOWN_SENDER)

	def test_failed_gate_fails_closed(self):
		doc = self.issue(raised_by=DESK_USER)
		with patch.object(assistant, "model_allowed", side_effect=RuntimeError("boom")), patch(
			"phamos.ai_agents.runner.frappe.log_error"
		):
			run = self.run_assistant(doc)
		self.assertIn(frappe._("AI model not used: the check could not run."), run.summary)
		self.assertEqual(
			frappe.db.get_value("AI Skill", {"agent": setup.ASSISTANT_NAME, "handler": "check_gate"}, "on_fail"),
			"Stop Run",
		)

	def test_unknown_sender_does_not_go(self):
		doc = self.issue(raised_by="someone@unknown.example")
		gate = assistant.model_allowed(doc)
		self.assertEqual((gate["allowed"], gate["reason"]), (False, assistant.UNKNOWN_SENDER))

	def test_run_records_the_gate(self):
		doc = self.issue(raised_by="someone@unknown.example")
		run = self.run_assistant(doc)
		self.assertIn("gate_unknown_sender", run.run_flags)


class TestBriefInChat(IssueAssistantTestCase):
	def test_bot_posts_the_brief_in_the_issue_chat(self):
		if "raven" not in frappe.get_installed_apps():
			self.skipTest("Raven is not installed")
		if not frappe.get_all("Raven Workspace", limit=1):
			self.skipTest("No Raven Workspace")
		frappe.db.set_single_value("phamos Settings", "enable_issue_chat", 1)
		doc = self.issue(raised_by=DESK_USER)
		self.run_assistant(doc)
		channel = frappe.db.get_value("Raven Channel", {"linked_doctype": "Issue", "linked_document": doc.name})
		self.assertTrue(channel)
		bot_user = frappe.db.get_value("Raven Bot", setup.ASSISTANT_NAME, "raven_user")
		texts = frappe.get_all(
			"Raven Message", filters={"channel_id": channel, "is_bot_message": 1}, pluck="text"
		)
		self.assertTrue(any(doc.name in (t or "") for t in texts), texts)
		self.assertTrue(frappe.db.exists("Raven Channel Member", {"channel_id": channel, "user_id": bot_user}))
