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
		# no test talks to Mistral; TestClassify patches its own answers on top (#2113)
		patch("phamos.ai_agents.agents.issue_classify.llm.chat_json", return_value=({}, "mistral-test")).start()
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


class TestManualRun(IssueAssistantTestCase):
	def checks(self, doc):
		return {c["key"]: c for c in assistant.get_manual_run_info(doc.name)["checks"]}

	def test_dialog_names_what_is_missing(self):
		self.settings.enabled = 0
		self.settings.save(ignore_permissions=True)
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		info = assistant.get_manual_run_info(doc.name)
		checks = {c["key"]: c for c in info["checks"]}
		self.assertFalse(info["would_start"])
		self.assertFalse(info["model_allowed"])
		self.assertFalse(checks["settings_enabled"]["ok"])
		self.assertFalse(checks["customer_ai_allowed"]["ok"])
		self.assertIn(CUSTOMER, checks["customer_ai_allowed"]["needed"])

	def test_all_green_is_not_an_override(self):
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 1)
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		self.assertTrue(all(c["ok"] for c in self.checks(doc).values()))
		with patch("phamos.ai_agents.runner.frappe.enqueue"):
			result = assistant.start_manual_run(doc.name)
		self.assertTrue(result["queued"])
		run = frappe.get_doc("AI Agent Run", result["run"])
		self.assertEqual((run.trigger, run.manual_override), ("Manual", 0))
		frappe.cache.delete(frappe.cache.make_key(f"ai_agent_run_lock:Issue:{doc.name}"))

	def test_override_runs_past_the_gate_and_is_recorded(self):
		self.settings.enabled = 0
		self.settings.save(ignore_permissions=True)
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		reasons = [f"{c['label']}: {c['current']}" for c in self.checks(doc).values() if not c["ok"]]
		run = runner.run_now("Issue", doc.name, trigger="Manual", override_reasons=reasons)
		self.assertEqual(run.status, "Completed", run.error)
		self.assertEqual(run.manual_override, 1)
		self.assertIn(CUSTOMER, run.override_reasons)
		gate = frappe.parse_json(run.analysis)["gate"]
		self.assertEqual((gate["allowed"], gate["reason"], gate["checked_reason"]),
			(True, assistant.MANUAL_OVERRIDE, assistant.CUSTOMER_NOT_ALLOWED))
		self.assertIn("manual override", run.summary)

	def test_override_starts_a_disabled_agent(self):
		frappe.db.set_value("AI Agent", setup.ASSISTANT_NAME, "enabled", 0)
		doc = self.issue(raised_by=WEBSITE_USER)
		self.assertIsNone(runner.get_agent("Issue"))
		run = runner.run_now("Issue", doc.name, trigger="Manual", override_reasons=["AI Agent disabled"])
		self.assertEqual(run.status, "Completed", run.error)

	def test_needs_write_permission(self):
		doc = self.issue(raised_by=WEBSITE_USER)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(WEBSITE_USER)
		with self.assertRaises(frappe.PermissionError):
			assistant.start_manual_run(doc.name)

	def test_run_result_shows_the_brief(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		run = runner.run_now("Issue", doc.name, trigger="Manual", override_reasons=["x"])
		result = assistant.get_run_result(run.name)
		self.assertEqual((result.status, result.manual_override), ("Completed", 1))
		self.assertIn(doc.name, result.summary)
		self.assertIn(self.assistant, result.assigned)
		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(WEBSITE_USER)
		with self.assertRaises(frappe.PermissionError):
			assistant.get_run_result(run.name)


class TestClassify(IssueAssistantTestCase):
	"""#2113: the model reads the Issue; llm.chat_json is patched, nothing goes to the network."""

	OTHER_CUSTOMER = "Issue Assistant Other Customer"

	def setUp(self):
		super().setUp()
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 1)
		self.project = frappe.get_doc(
			{"doctype": "Project", "project_name": "Issue Assistant Classify Test", "customer": CUSTOMER,
			 "users": [{"user": DESK_USER}]}
		).insert(ignore_permissions=True).name
		if not frappe.db.exists("Customer", self.OTHER_CUSTOMER):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": self.OTHER_CUSTOMER,
				 "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				 "territory": frappe.db.get_value("Territory", {"is_group": 0})}
			).insert(ignore_permissions=True)
		self.issue_type = self.ensure_issue_type("Assistant Bug")

	def ensure_issue_type(self, name):
		if not frappe.db.exists("Issue Type", name):
			frappe.get_doc({"doctype": "Issue Type", "__newname": name}).insert(ignore_permissions=True)
		return name

	def answer(self, confidence="strong", person=DESK_USER, priority="High"):
		return {
			"summary": "The invoice print shows the wrong VAT.",
			"missing": ["which invoice"],
			"issue_type": {"value": self.issue_type, "confidence": confidence, "reason": "a defect"},
			"priority": {"value": priority, "confidence": confidence, "reason": "invoices go out today"},
			"person": {"user": person, "confidence": confidence, "reason": "project member"},
		}

	def classify(self, doc, answer=None, **run_args):
		with patch("phamos.ai_agents.agents.issue_classify.llm.chat_json",
				return_value=(answer or self.answer(), "mistral-test")) as chat:
			run = runner.run_now("Issue", doc.name, trigger=run_args.pop("trigger", "Insert"), **run_args)
		self.assertEqual(run.status, "Completed", run.error)
		self.chat = chat
		return run

	def test_gate_not_allowed_means_no_model_call(self):
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 0)
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		run = self.classify(doc)
		self.chat.assert_not_called()
		self.assertIn(frappe._("AI model not used: AI processing is not allowed for customer {0}.").format(CUSTOMER),
			run.summary)
		self.assertFalse(run.llm_calls)

	def test_manual_override_calls_the_model(self):
		# decision 7: a manual override also sends the Issue to the model
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 0)
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		self.classify(doc, trigger="Manual", override_reasons=["Customer allows AI processing: No"])
		self.chat.assert_called_once()

	def test_type_set_when_empty_and_reporter_priority_stays(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project, priority="Low")
		run = self.classify(doc)
		doc.reload()
		self.assertEqual(doc.issue_type, self.issue_type)
		self.assertEqual(doc.priority, "Low")
		self.assertIn("issue_type", run.fields_set)
		self.assertNotIn("priority", run.fields_set)
		self.assertIn("High", run.summary)  # the disagreement is in the brief
		self.assertEqual((run.llm_calls, run.llm_model), (1, "mistral-test"))

	def test_review_confidence_writes_nothing(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project)
		self.classify(doc, self.answer(confidence="review"))
		doc.reload()
		self.assertFalse(doc.issue_type)
		self.assertNotIn(DESK_USER, self.assignees(doc))

	def test_strong_and_high_assigns_the_person(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project, priority="High")
		run = self.classify(doc)
		self.assertIn(DESK_USER, self.assignees(doc))
		self.assertIn(frappe._("Assigned {0}: {1}").format(frappe.utils.get_fullname(DESK_USER), "project member"),
			run.summary)

	def test_strong_and_medium_only_suggests(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project, priority="Medium")
		run = self.classify(doc)
		self.assertNotIn(DESK_USER, self.assignees(doc))
		self.assertIn(frappe.utils.get_fullname(DESK_USER), run.summary)

	def test_values_outside_the_lists_are_ignored(self):
		answer = self.answer()
		answer["issue_type"]["value"] = "Not A Type"
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project)
		run = self.classify(doc, answer)
		doc.reload()
		self.assertFalse(doc.issue_type)
		self.assertNotIn("Not A Type", run.summary)

	def test_an_echoed_prompt_is_still_read(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project)
		run = self.classify(doc, {"issue": {}, "answer_format": self.answer()})
		self.assertIn("wrong VAT", run.summary)

	def test_person_outside_the_candidates_is_ignored(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project, priority="High")
		self.classify(doc, self.answer(person="someone-else@example.com"))
		self.assertEqual(self.assignees(doc), {self.assistant})

	def test_prompt_has_no_other_customer(self):
		self.issue(raised_by=WEBSITE_USER, customer=self.OTHER_CUSTOMER, subject="Other customer's Issue")
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project)
		self.classify(doc)
		prompt = self.chat.call_args.args[0]
		self.assertIn(CUSTOMER, prompt)
		self.assertNotIn(self.OTHER_CUSTOMER, prompt)
		self.assertNotIn("Other customer's Issue", prompt)

	def test_screenshot_goes_as_image_only_when_allowed(self):
		png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		file_doc = frappe.get_doc({"doctype": "File", "file_name": f"phriend-{doc.name}.png", "is_private": 1,
			"attached_to_doctype": "Issue", "attached_to_name": doc.name, "content": png}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", file_doc.name, force=True, ignore_permissions=True))
		doc.db_set("phriend_screenshot", file_doc.file_url)
		self.classify(doc)
		self.assertEqual(self.chat.call_args.kwargs["images"], [("image/png", png)])

		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 0)
		self.classify(doc)
		self.chat.assert_not_called()

	def test_model_not_configured_keeps_the_code_brief(self):
		from phamos.ai_agents import llm

		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		with patch("phamos.ai_agents.agents.issue_classify.llm.chat_json",
				side_effect=llm.LLMNotConfigured("Mistral is not configured")):
			run = runner.run_now("Issue", doc.name, trigger="Insert")
		self.assertEqual(run.status, "Completed", run.error)
		self.assertIn("Mistral is not configured", run.summary)
		self.assertIn(doc.name, run.summary)
