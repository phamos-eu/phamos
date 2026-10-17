# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue chat (#1614): one Private Raven channel per Issue, members from owner and assignees."""

from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.tests.utils import FrappeTestCase

from phamos.api import issue_chat
from phamos.api import personal_cockpit as pc
from phamos.api import sales_spa

OWNER = "issue-chat-owner@example.com"
ASSIGNEE = "issue-chat-assignee@example.com"
LATECOMER = "issue-chat-latecomer@example.com"
OUTSIDER = "issue-chat-outsider@example.com"  # no Raven role
NO_READER = "issue-chat-noreader@example.com"  # Raven user who cannot read Issues
WORKSPACE = "issue-chat-test"

# Issue needs Support Team; Raven creates the Raven User for the "Raven User" role.
ROLES = ("Support Team", "Raven User")


def _ensure_user(email, roles=ROLES):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)
	return email


def _mention(user):
	return f'<span class="mention" data-type="userMention" data-id="{user}" data-label="{user}">@{user}</span>'


def _send(channel_id, html):
	from raven.api.raven_message import send_message

	return send_message(channel_id=channel_id, text=f"<p>{html}</p>")


def _system_lines(channel_id):
	return frappe.get_all(
		"Raven Message",
		filters={"channel_id": channel_id, "message_type": "System"},
		pluck="text",
		order_by="creation asc",
	)


def _members(channel_id):
	return set(
		frappe.get_all("Raven Channel Member", filters={"channel_id": channel_id}, pluck="user_id")
	)


@skipUnless("raven" in frappe.get_installed_apps(), "Raven is not installed")
class TestIssueChat(FrappeTestCase):
	def setUp(self):
		# assign_to.add e-mails at once in tests, and the Email Queue commits (see memory notes).
		mute = patch("frappe.desk.form.assign_to.notify_assignment")
		mute.start()
		self.addCleanup(mute.stop)

		for user in (OWNER, ASSIGNEE, LATECOMER):
			_ensure_user(user)
		_ensure_user(OUTSIDER, roles=("Support Team",))
		# Raven may auto-add every System User (Raven Settings); this one must have no Raven user.
		frappe.db.delete("Raven User", {"user": OUTSIDER})
		_ensure_user(NO_READER, roles=("Raven User",))
		if not frappe.db.exists("Raven Workspace", WORKSPACE):
			frappe.get_doc(
				{"doctype": "Raven Workspace", "workspace_name": WORKSPACE, "type": "Private"}
			).insert(ignore_permissions=True)
		frappe.db.set_single_value("phamos Settings", "enable_issue_chat", 1)
		frappe.db.set_single_value("phamos Settings", "issue_chat_workspace", WORKSPACE)

		frappe.set_user(OWNER)
		self.issue = frappe.get_doc(
			{"doctype": "Issue", "subject": "Issue chat test", "raised_by": OWNER}
		).insert()
		self._assign(ASSIGNEE)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _assign(self, user):
		add_assignment(
			{"doctype": "Issue", "name": self.issue.name, "assign_to": [user], "description": "chat"}
		)

	def test_no_chat_yet(self):
		state = pc.get_issue_chat(self.issue.name)
		self.assertTrue(state["enabled"])
		self.assertIsNone(state["channel_id"])
		self.assertFalse(state["is_member"])

	def test_disabled_reports_and_refuses(self):
		frappe.db.set_single_value("phamos Settings", "enable_issue_chat", 0)
		self.assertFalse(pc.get_issue_chat(self.issue.name)["enabled"])
		with self.assertRaises(frappe.ValidationError):
			pc.ensure_issue_chat(self.issue.name)

	def test_start_creates_private_linked_channel_with_owner_and_assignees(self):
		state = pc.ensure_issue_chat(self.issue.name)

		channel = frappe.get_doc("Raven Channel", state["channel_id"])
		self.assertEqual(channel.type, "Private")
		self.assertEqual(channel.workspace, WORKSPACE)
		self.assertEqual((channel.linked_doctype, channel.linked_document), ("Issue", self.issue.name))
		self.assertEqual(_members(channel.name), {OWNER, ASSIGNEE})
		self.assertTrue(
			frappe.db.get_value(
				"Raven Channel Member", {"channel_id": channel.name, "user_id": OWNER}, "is_admin"
			)
		)
		self.assertTrue(
			frappe.db.exists("Raven Workspace Member", {"user": ASSIGNEE, "workspace": WORKSPACE})
		)
		self.assertEqual(state["url"], f"/raven/{WORKSPACE}/{channel.name}")
		self.assertTrue(state["is_member"])
		self.assertEqual(state["unread"], 0)  # their own intro message

		intro = frappe.get_all(
			"Raven Message",
			filters={"channel_id": channel.name, "message_type": ("!=", "System")},
			fields=["link_doctype", "link_document", "text"],
		)
		self.assertEqual(len(intro), 1)
		self.assertEqual((intro[0].link_doctype, intro[0].link_document), ("Issue", self.issue.name))

	def test_start_again_reuses_the_channel(self):
		first = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.assertEqual(pc.ensure_issue_chat(self.issue.name)["channel_id"], first)
		self.assertEqual(
			frappe.db.count("Raven Channel", {"linked_doctype": "Issue", "linked_document": self.issue.name}),
			1,
		)
		self.assertEqual(
			frappe.db.count("Raven Message", {"channel_id": first, "message_type": ("!=", "System")}), 1
		)

	def test_new_assignee_joins_and_unassigned_stays(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]

		self._assign(LATECOMER)
		self.assertIn(LATECOMER, _members(channel_id))

		remove_assignment("Issue", self.issue.name, ASSIGNEE)
		self.assertIn(ASSIGNEE, _members(channel_id))

	def test_reader_who_is_not_a_member_can_join(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		frappe.set_user(LATECOMER)  # Support Team reads every Issue

		# Cockpit scope is tested below; the join itself lives in the shared service.
		doc = frappe.get_doc("Issue", self.issue.name)
		self.assertFalse(issue_chat.get_chat(doc)["is_member"])
		self.assertTrue(issue_chat.ensure_chat(doc)["is_member"])
		self.assertIn(LATECOMER, _members(channel_id))

	def test_out_of_scope_user_gets_no_chat(self):
		pc.ensure_issue_chat(self.issue.name)
		frappe.set_user(LATECOMER)  # neither owner nor assignee: not in the Personal Cockpit
		with self.assertRaises(frappe.ValidationError):
			pc.get_issue_chat(self.issue.name)
		with self.assertRaises(frappe.ValidationError):
			pc.ensure_issue_chat(self.issue.name)

	def test_assignee_without_raven_user_is_skipped(self):
		self._assign(OUTSIDER)
		state = pc.ensure_issue_chat(self.issue.name)
		self.assertNotIn(OUTSIDER, _members(state["channel_id"]))
		self.assertEqual([u["user"] for u in state["skipped_users"]], [OUTSIDER])

	def test_unread_counts_and_states(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		frappe.set_user(ASSIGNEE)
		frappe.db.set_value(
			"Raven Channel Member",
			{"channel_id": channel_id, "user_id": ASSIGNEE},
			"last_visit",
			"2000-01-01 00:00:00",
		)
		states = pc.get_issue_chat_states(frappe.as_json([self.issue.name, "ISS-DOES-NOT-EXIST"]))
		self.assertEqual(list(states), [self.issue.name])
		self.assertEqual(states[self.issue.name]["channel_id"], channel_id)
		self.assertTrue(states[self.issue.name]["is_member"])
		self.assertEqual(states[self.issue.name]["unread"], 1)  # the intro message
		intro = frappe.get_all(
			"Raven Message",
			filters={"channel_id": channel_id, "message_type": ("!=", "System")},
			pluck="name",
		)[0]
		self.assertEqual(states[self.issue.name]["first_unread"], intro)
		self.assertEqual(pc.get_issue_chat(self.issue.name)["unread"], 1)


	def test_mentioned_reader_joins_the_chat(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.assertNotIn(LATECOMER, _members(channel_id))

		_send(channel_id, f"{_mention(LATECOMER)} can you have a look?")
		self.assertIn(LATECOMER, _members(channel_id))
		self.assertTrue(
			frappe.db.exists("Raven Workspace Member", {"user": LATECOMER, "workspace": WORKSPACE})
		)

	def test_mention_in_a_thread_adds_to_chat_and_thread(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		root = _send(channel_id, "Start of a side topic")
		thread_id = create_thread(root.name)["thread_id"]

		_send(thread_id, f"{_mention(LATECOMER)} this one is for you")
		self.assertIn(LATECOMER, _members(channel_id))
		self.assertIn(LATECOMER, _members(thread_id))

	def test_mention_of_someone_who_cannot_read_the_issue_adds_nobody(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		_send(channel_id, f"{_mention(NO_READER)} FYI")
		self.assertNotIn(NO_READER, _members(channel_id))

	def test_mentions_outside_issue_chats_are_left_to_raven(self):
		other = frappe.get_doc(
			{
				"doctype": "Raven Channel",
				"channel_name": "issue-chat-test-plain",
				"type": "Private",
				"workspace": WORKSPACE,
			}
		).insert(ignore_permissions=True)
		_send(other.name, f"{_mention(LATECOMER)} hi")
		self.assertNotIn(LATECOMER, _members(other.name))

	def test_status_change_is_posted(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.issue.reload()
		self.issue.status = "On Hold"
		self.issue.save()
		self.assertTrue(any("set the status to On Hold" in t for t in _system_lines(channel_id)))
		self.assertFalse(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))

	def test_closing_archives_and_reopening_restores(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.issue.reload()
		self.issue.status = "Closed"
		self.issue.save()
		self.assertTrue(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))
		state = pc.get_issue_chat(self.issue.name)
		self.assertTrue(state["archived"])
		# Starting again finds the archived chat instead of creating a second one.
		self.assertEqual(pc.ensure_issue_chat(self.issue.name)["channel_id"], channel_id)

		self.issue.reload()
		self.issue.status = "Open"
		self.issue.save()
		self.assertFalse(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))
		lines = _system_lines(channel_id)
		self.assertTrue(any("set the status to Closed" in t for t in lines))
		self.assertTrue(any("set the status to Open" in t for t in lines))

	def test_assignments_are_posted_once(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		before = len(_system_lines(channel_id))

		self._assign(LATECOMER)
		new_lines = _system_lines(channel_id)[before:]
		self.assertEqual(len(new_lines), 1, new_lines)  # no extra "added" line from Raven
		self.assertIn("assigned", new_lines[0])
		self.assertIn(LATECOMER, _members(channel_id))

		remove_assignment("Issue", self.issue.name, LATECOMER)
		self.assertIn("unassigned", _system_lines(channel_id)[-1])
		self.assertIn(LATECOMER, _members(channel_id))

	def test_conversion_to_task_is_posted(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		frappe.set_user("Administrator")
		task = frappe.get_doc(
			{"doctype": "Task", "subject": "From the chat test", "issue": self.issue.name}
		).insert()
		self.assertTrue(any(f"converted this Issue to Task {task.name}" in t for t in _system_lines(channel_id)))

	def test_unread_thread_replies_are_counted(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		root = _send(channel_id, "A side topic")
		# The assignee starts the thread on the owner's message: both take part in it.
		frappe.set_user(ASSIGNEE)
		thread_id = create_thread(root.name)["thread_id"]
		_send(thread_id, "a reply")
		_send(thread_id, "and another one")
		_send(thread_id, "<b>one more</b>")

		frappe.set_user(OWNER)
		frappe.db.set_value(
			"Raven Channel Member",
			{"channel_id": thread_id, "user_id": OWNER},
			"last_visit",
			"2000-01-01 00:00:00",
		)
		state = pc.get_issue_chat(self.issue.name)
		self.assertEqual(state["unread_threads"], 3)
		self.assertEqual(len(state["threads"]), 1)
		self.assertEqual(state["threads"][0]["thread_id"], thread_id)
		self.assertEqual(state["threads"][0]["unread"], 3)
		self.assertEqual(state["threads"][0]["preview"], "A side topic")
		self.assertTrue(state["threads"][0]["last_sender"])
		states = pc.get_issue_chat_states(frappe.as_json([self.issue.name]))
		self.assertEqual(states[self.issue.name]["unread_threads"], 3)
		# Nothing new in the chat itself: the list opens the thread.
		self.assertIsNone(states[self.issue.name]["first_unread"])
		self.assertEqual(states[self.issue.name]["first_unread_thread"], thread_id)

		# Someone who is not in the thread has nothing unread there.
		frappe.set_user(LATECOMER)
		pc_state = issue_chat.get_chat(frappe.get_doc("Issue", self.issue.name))
		self.assertEqual(pc_state["unread_threads"], 0)

	def test_my_unread_chats(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.assertEqual(pc.get_unread_issue_chats()["total"], 0)  # only my own intro so far

		frappe.set_user(ASSIGNEE)
		message = _send(channel_id, "News for the owner")
		frappe.set_user(OWNER)
		result = pc.get_unread_issue_chats()
		self.assertEqual(result["total"], 1)
		chat = result["chats"][0]
		self.assertEqual(chat["name"], self.issue.name)
		self.assertEqual(chat["subject"], "Issue chat test")
		self.assertEqual(chat["unread"], 1)
		self.assertEqual(chat["first_unread"], message.name)
		self.assertTrue(chat["last_sender"])

		# A closed Issue's chat is archived and drops out.
		self.issue.reload()
		self.issue.status = "Closed"
		self.issue.save()
		self.assertEqual(pc.get_unread_issue_chats()["total"], 0)

	def test_raven_links_open_the_matching_cockpit(self):
		self.assertEqual(
			issue_chat.document_link("Issue", self.issue.name),
			f"/personal-cockpit/issues/list/{self.issue.name}",
		)
		self.assertIsNone(issue_chat.document_link("Task", "TASK-0001"))

		frappe.set_user("Administrator")
		department = frappe.get_all("Department", pluck="name", limit=1)
		if not department or not frappe.get_meta("Issue").has_field("custom_department"):
			return
		frappe.db.set_single_value("phamos Settings", "sales_department", department[0])
		frappe.db.set_value("Issue", self.issue.name, "custom_department", department[0])
		self.assertEqual(
			issue_chat.document_link("Issue", self.issue.name),
			f"/sales-cockpit/issues/list/{self.issue.name}",
		)

	def test_every_cockpit_exposes_the_chat_endpoints(self):
		endpoints = ("get_issue_chat", "ensure_issue_chat", "get_issue_chat_states")
		for module in (pc, sales_spa):
			for name in endpoints:
				self.assertIn(getattr(module, name), frappe.whitelisted, f"{module.__name__}.{name}")
