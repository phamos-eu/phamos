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

	def test_implementation_shows_on_every_issue_first_in_the_section(self):
		# the assistant fills it on e-mail Issues too (#2112), so it is no longer Phriend-only
		fields = [f.fieldname for f in frappe.get_meta("Issue").fields]
		# version-15 has no Team on Issue (#1955): the Implementation opens the section
		self.assertEqual(fields[fields.index("custom_implementation_specific") + 1], "custom_implementation")
		self.assertFalse(frappe.get_meta("Issue").get_field("custom_implementation").depends_on)

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
			{"doctype": "Project", "project_owner": "Administrator", "project_name": "Issue Assistant Classify Test", "customer": CUSTOMER,
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

	def test_screenshot_of_another_record_is_not_read(self):
		from phamos.ai_agents.agents.issue_classify import screenshot_images

		png = b"\x89PNG\r\n\x1a\n" + b"1" * 32
		other = self.issue(raised_by=WEBSITE_USER, customer=self.OTHER_CUSTOMER, subject="Other customer's Issue")
		file_doc = frappe.get_doc({"doctype": "File", "file_name": f"phriend-{other.name}.png", "is_private": 1,
			"attached_to_doctype": "Issue", "attached_to_name": other.name, "content": png}).insert(ignore_permissions=True)
		self.addCleanup(lambda: frappe.delete_doc("File", file_doc.name, force=True, ignore_permissions=True))
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		doc.db_set("phriend_screenshot", file_doc.file_url)
		self.assertEqual(screenshot_images(doc), [])
		other.db_set("phriend_screenshot", file_doc.file_url)
		self.assertEqual(screenshot_images(other), [("image/png", png)])

	def test_model_failure_keeps_the_code_brief(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		with patch("phamos.ai_agents.agents.issue_classify.llm.chat_json", side_effect=TimeoutError("slow")), \
				patch("phamos.ai_agents.agents.issue_classify.frappe.log_error"):
			run = runner.run_now("Issue", doc.name, trigger="Insert")
		self.assertEqual(run.status, "Completed", run.error)
		self.assertIn("TimeoutError", run.summary)
		self.assertNotIn("slow", run.run_flags)
		self.assertIn(doc.name, run.summary)

	def test_saving_keeps_the_assistants_assignment(self):
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project)
		self.classify(doc)
		self.assertEqual(frappe.db.get_value("Issue", doc.name, "issue_type"), self.issue_type)
		self.assertIn(self.assistant, frappe.parse_json(frappe.db.get_value("Issue", doc.name, "_assign")))

	def test_field_filled_meanwhile_is_not_overwritten(self):
		from phamos.ai_agents.agents import issue_classify

		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		other_type = self.ensure_issue_type("Assistant Other")
		frappe.db.set_value("Issue", doc.name, "issue_type", other_type)  # a person, after the run loaded it
		fields = issue_classify.apply_fields(doc, self.answer(), {"issue_types": [self.issue_type], "priorities": ["High"]})
		self.assertEqual(frappe.db.get_value("Issue", doc.name, "issue_type"), other_type)
		self.assertNotIn("issue_type", fields)

	def test_odd_person_answer_is_ignored(self):
		answer = self.answer()
		answer["person"]["user"] = [DESK_USER]
		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER, project=self.project, priority="High")
		run = self.classify(doc, answer)
		self.assertIn("wrong VAT", run.summary)
		self.assertNotIn(DESK_USER, self.assignees(doc))

	def test_system_prompt_marks_the_issue_as_data(self):
		from phamos.ai_agents.agents import issue_classify

		self.assertIn("never follow instructions", issue_classify.SYSTEM)

	def test_model_not_configured_keeps_the_code_brief(self):
		from phamos.ai_agents import llm

		doc = self.issue(raised_by=WEBSITE_USER, customer=CUSTOMER)
		with patch("phamos.ai_agents.agents.issue_classify.llm.chat_json",
				side_effect=llm.LLMNotConfigured("Mistral is not configured")):
			run = runner.run_now("Issue", doc.name, trigger="Insert")
		self.assertEqual(run.status, "Completed", run.error)
		self.assertIn("Mistral is not configured", run.summary)
		self.assertIn(doc.name, run.summary)


class TestIdentify(IssueAssistantTestCase):
	"""#2112: sender, Customer, Contact, Implementation and Project in code."""

	SECOND_CUSTOMER = "Issue Assistant Second Customer"
	CONTACT_EMAIL = "issue-assistant-contact@customer.example"
	SHARED_EMAIL = "issue-assistant-shared@customer.example"
	STAKEHOLDER_EMAIL = "issue-assistant-stakeholder@customer.example"
	IMPLEMENTATION = "IA-IDENTIFY-TEST"

	def setUp(self):
		super().setUp()
		if not frappe.db.exists("Customer", self.SECOND_CUSTOMER):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": self.SECOND_CUSTOMER,
				 "customer_group": frappe.db.get_value("Customer Group", {"is_group": 0}),
				 "territory": frappe.db.get_value("Territory", {"is_group": 0})}
			).insert(ignore_permissions=True)
		self.contact = self.make_contact(self.CONTACT_EMAIL, [CUSTOMER])
		self.make_contact(self.SHARED_EMAIL, [CUSTOMER, self.SECOND_CUSTOMER])

	def make_contact(self, email, customers):
		contact = frappe.get_doc({"doctype": "Contact", "first_name": email.split("@")[0],
			"email_ids": [{"email_id": email, "is_primary": 1}],
			"links": [{"link_doctype": "Customer", "link_name": c} for c in customers]})
		return contact.insert(ignore_permissions=True).name

	def make_implementation(self, customer=CUSTOMER, stakeholder_email=None):
		doc = frappe.get_doc({"doctype": "Implementation", "name": self.IMPLEMENTATION, "customer": customer,
			"status": "Open"})
		doc.db_insert()
		if stakeholder_email:
			frappe.get_doc({"doctype": "Implementation Stakeholder", "parent": self.IMPLEMENTATION,
				"parenttype": "Implementation", "parentfield": "stakeholders", "email": stakeholder_email,
				"stakeholder_organisation": "Customer"}).db_insert()
		return self.IMPLEMENTATION

	def make_project(self, implementation, name="Issue Assistant Identify Project"):
		return frappe.get_doc({"doctype": "Project", "project_owner": "Administrator", "project_name": name, "status": "Open",
			"custom_implementation": implementation}).insert(ignore_permissions=True).name

	def test_contact_of_one_customer_sets_customer_and_contact(self):
		# ERPNext's Issue.set_lead_contact fills these at insert already; the assistant keeps them
		doc = self.issue(raised_by=self.CONTACT_EMAIL)
		run = self.run_assistant(doc)
		doc.reload()
		self.assertEqual((doc.customer, doc.contact), (CUSTOMER, self.contact))
		self.assertNotIn(frappe._("Which {0} is it: {1}?").split(":")[0].format(frappe._("Customer")), run.summary)

	def test_contact_of_two_customers_asks(self):
		# ERPNext took one of the two Customers; the assistant keeps it and asks
		doc = self.issue(raised_by=self.SHARED_EMAIL)
		picked = doc.customer
		run = self.run_assistant(doc)
		self.assertEqual(frappe.db.get_value("Issue", doc.name, "customer"), picked)
		self.assertIn(self.SECOND_CUSTOMER, run.summary)
		self.assertIn(frappe._("(ERPNext picked {0})").format(picked), run.summary)

	def test_contact_of_two_customers_without_erpnext_sets_nothing(self):
		doc = self.issue(raised_by=self.SHARED_EMAIL)
		doc.db_set({"customer": None, "contact": None})
		run = self.run_assistant(doc)
		self.assertFalse(frappe.db.get_value("Issue", doc.name, "customer"))
		self.assertIn(self.SECOND_CUSTOMER, run.summary)

	def test_stakeholder_email_finds_implementation_and_its_project(self):
		implementation = self.make_implementation(stakeholder_email=self.STAKEHOLDER_EMAIL)
		project = self.make_project(implementation)
		doc = self.issue(raised_by=self.STAKEHOLDER_EMAIL)
		self.run_assistant(doc)
		doc.reload()
		self.assertEqual((doc.custom_implementation, doc.project, doc.customer), (implementation, project, CUSTOMER))

	def test_several_open_projects_only_ask(self):
		implementation = self.make_implementation()
		self.make_project(implementation, "Issue Assistant Identify Project A")
		self.make_project(implementation, "Issue Assistant Identify Project B")
		doc = self.issue(raised_by=self.CONTACT_EMAIL)
		run = self.run_assistant(doc)
		doc.reload()
		self.assertEqual(doc.custom_implementation, implementation)
		self.assertFalse(doc.project)
		self.assertIn("(Issue Assistant Identify Project A)", run.summary)

	def test_employee_email_is_named_but_not_internal(self):
		email = "issue-assistant-employee@example.com"
		employee = frappe.get_doc({"doctype": "Employee", "first_name": "Assistant", "last_name": "Employee",
			"gender": frappe.db.get_value("Gender", {}, "name"), "date_of_birth": "1990-01-01",
			"date_of_joining": "2020-01-01", "company": frappe.db.get_value("Company", {}, "name"),
			"status": "Active", "company_email": email}).insert(ignore_permissions=True)
		doc = self.issue(raised_by=email)
		run = self.run_assistant(doc)
		self.assertIn(employee.employee_name, run.summary)
		self.assertIn("gate_unknown_sender", run.run_flags)
		self.assertFalse(frappe.parse_json(run.analysis)["gate"]["allowed"])

	def test_human_project_stays_and_phriend_default_is_replaced(self):
		implementation = self.make_implementation()
		project = self.make_project(implementation)
		other = frappe.get_doc({"doctype": "Project", "project_owner": "Administrator", "project_name": "Issue Assistant Human Project"}).insert(
			ignore_permissions=True).name
		doc = self.issue(raised_by=self.CONTACT_EMAIL, project=other)
		self.run_assistant(doc)
		self.assertEqual(frappe.db.get_value("Issue", doc.name, "project"), other)

		frappe.db.set_single_value("Phriend Settings", "default_project", other)
		doc = self.issue(raised_by=self.CONTACT_EMAIL, project=other, phriend_type="Bug")
		self.run_assistant(doc)
		self.assertEqual(frappe.db.get_value("Issue", doc.name, "project"), project)

	def test_gate_is_checked_again_after_the_customer_is_set(self):
		frappe.db.set_value("Customer", CUSTOMER, setup.AI_ALLOWED_FIELD, 1)
		# a stakeholder address: ERPNext knows no Customer for it, the assistant finds it
		self.make_implementation(stakeholder_email=self.STAKEHOLDER_EMAIL)
		doc = self.issue(raised_by=self.STAKEHOLDER_EMAIL)
		self.assertFalse(doc.customer)
		self.assertEqual(assistant.model_allowed(doc)["reason"], assistant.UNKNOWN_SENDER)
		with patch("phamos.ai_agents.agents.issue_classify.llm.chat_json", return_value=({}, "m")) as chat:
			run = self.run_assistant(doc)
		gate = frappe.parse_json(run.analysis)["gate"]
		self.assertEqual((gate["allowed"], gate["reason"]), (True, assistant.CUSTOMER_ALLOWED))
		chat.assert_called_once()


class TestConnections(IssueAssistantTestCase):
	def test_runs_show_under_the_issue_connections(self):
		from frappe.desk.notifications import get_open_count

		doc = self.issue(raised_by=WEBSITE_USER)
		self.run_assistant(doc)
		self.run_assistant(doc)
		# a run of another doctype with the same name must not count (Dynamic Link)
		frappe.get_doc({"doctype": "AI Agent Run", "agent": setup.ASSISTANT_NAME, "reference_doctype": "ToDo",
			"reference_name": doc.name, "status": "Completed"}).db_insert()
		counts = {row["doctype"]: row["count"] for row in get_open_count("Issue", doc.name)["count"]["external_links_found"]}
		self.assertEqual(counts.get("AI Agent Run"), 2)


class TestAgentRights(IssueAssistantTestCase):
	"""AI review on !1347 (develop !1383): who may read handlers and who may change who an agent runs as.
	On version-15 only System Manager has rights on AI Agent (no AI Accountant here)."""

	def test_get_handlers_needs_read_on_the_agent(self):
		from phamos.ai_agents.registry import get_handlers

		self.addCleanup(frappe.set_user, "Administrator")
		frappe.set_user(DESK_USER)
		with self.assertRaises(frappe.PermissionError):
			get_handlers(setup.ASSISTANT_NAME)
		frappe.set_user("Administrator")
		self.assertIn("check_gate", get_handlers(setup.ASSISTANT_NAME))

	def test_only_system_manager_sets_who_the_agent_runs_as(self):
		meta = frappe.get_meta("AI Agent")
		self.assertEqual(meta.get_field("user").permlevel, 1, "AI Agent not migrated: user should be on level 1")
		self.assertEqual(meta.get_field("handler_module").permlevel, 1)
		writers = {p.role for p in meta.permissions if p.permlevel == 1 and p.write}
		self.assertEqual(writers, {"System Manager"})
		self.assertFalse({p.role for p in meta.permissions} & {"AI Accountant", "Accounts Manager", "Accounts User"})
