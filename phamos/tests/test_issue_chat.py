# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Record chat (#1614, #1779): one Private Raven channel per Issue or Task, members from owner and
assignees."""

from unittest import skipUnless
from unittest.mock import patch

import frappe
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.desk.form.load import get_assignments
from frappe.tests.utils import FrappeTestCase

from phamos.api import accounting_spa
from phamos.api import human_resources_spa
from phamos.api import issue_chat
from phamos.api import personal_cockpit as pc
from phamos.api import project_management_spa
from phamos.api import sales_spa
from phamos.api import software_development_spa

OWNER = "issue-chat-owner@example.com"
ASSIGNEE = "issue-chat-assignee@example.com"
LATECOMER = "issue-chat-latecomer@example.com"
OUTSIDER = "issue-chat-outsider@example.com"  # no Raven role
NO_READER = "issue-chat-noreader@example.com"  # Raven user who cannot read Issues
WORKSPACE = "issue-chat-test"

# Issue needs Support Team, Task Projects User; Raven creates the Raven User for the "Raven User"
# role.
ROLES = ("Support Team", "Projects User", "Raven User")


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
		# Restored in tearDown: adding the Raven index (DDL) commits the open transaction, so the
		# rollback alone left the site's chat pointed at the test workspace.
		self._settings = {
			field: frappe.db.get_single_value("phamos Settings", field)
			for field in ("enable_issue_chat", "issue_chat_workspace", "personal_ideas_show_author")
		}
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
		changed = {
			field: value
			for field, value in self._settings.items()
			if frappe.db.get_single_value("phamos Settings", field) != value
		}
		if changed:
			for field, value in changed.items():
				frappe.db.set_single_value("phamos Settings", field, value)
			frappe.db.commit()  # nosemgrep: undoing what a DDL statement committed

	def _assign(self, user, doctype="Issue", name=None):
		add_assignment(
			{"doctype": doctype, "name": name or self.issue.name, "assign_to": [user], "description": "chat"}
		)

	def _task(self, **fields):
		"""A Task of OWNER assigned to ASSIGNEE (in OWNER's Personal Cockpit scope)."""
		task = frappe.get_doc({"doctype": "Task", "subject": "Task chat test", **fields}).insert()
		self._assign(ASSIGNEE, "Task", task.name)
		return task

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
		self.assertEqual(
			states[self.issue.name]["last_message_at"],
			frappe.db.get_value("Raven Channel", channel_id, "last_message_timestamp"),
		)
		self.assertTrue(states[self.issue.name]["last_message_at"])
		self.assertEqual(pc.get_issue_chat(self.issue.name)["unread"], 1)


	def test_unread_mentions_are_counted_in_chat_and_threads(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		_send(channel_id, "nothing for anyone in particular")

		def seen_long_ago(channel):
			frappe.db.set_value(
				"Raven Channel Member", {"channel_id": channel, "user_id": ASSIGNEE}, "last_visit", "2000-01-01"
			)

		def mentions():
			frappe.set_user(ASSIGNEE)
			states = pc.get_issue_chat_states(frappe.as_json([self.issue.name]))
			count = pc.get_issue_chat(self.issue.name)["mentions"]
			self.assertEqual(states[self.issue.name]["mentions"], count)
			frappe.set_user(OWNER)
			return count

		seen_long_ago(channel_id)
		self.assertEqual(mentions(), 0)  # new messages, but no mention: the bubble stays blue

		_send(channel_id, f"{_mention(ASSIGNEE)} please check")
		self.assertEqual(mentions(), 1)

		root = _send(channel_id, "A side topic")
		thread_id = create_thread(root.name)["thread_id"]
		_send(thread_id, f"{_mention(ASSIGNEE)} and this one")
		seen_long_ago(thread_id)
		self.assertEqual(mentions(), 2)

		# Reading the chat leaves the mention in the thread.
		frappe.db.set_value(
			"Raven Channel Member", {"channel_id": channel_id, "user_id": ASSIGNEE}, "last_visit", frappe.utils.now()
		)
		self.assertEqual(mentions(), 1)

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

	def _assigned(self, doctype="Issue", name=None):
		return {a.get("owner") for a in get_assignments(doctype, name or self.issue.name)}

	def test_mention_assigns_to_the_issue(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		self.assertNotIn(LATECOMER, self._assigned())

		_send(channel_id, f"{_mention(LATECOMER)} can you take this?")
		self.assertIn(LATECOMER, self._assigned())
		todo = frappe.db.get_value(
			"ToDo",
			{"reference_type": "Issue", "reference_name": self.issue.name, "allocated_to": LATECOMER},
			"description",
		)
		self.assertIn("mentioned you in the chat of Issue", todo)
		# The assignment shows up in the chat like any other.
		self.assertTrue(any("assigned" in t for t in _system_lines(channel_id)))

		# A second mention does not assign twice.
		_send(channel_id, f"{_mention(LATECOMER)} ping")
		self.assertEqual(
			frappe.db.count(
				"ToDo",
				{"reference_type": "Issue", "reference_name": self.issue.name, "allocated_to": LATECOMER, "status": "Open"},
			),
			1,
		)

	def test_mention_shows_as_unread_for_someone_it_brings_in(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		_send(channel_id, f"{_mention(LATECOMER)} can you take this?")
		frappe.set_user(LATECOMER)
		state = pc.get_issue_chat_states(frappe.as_json([self.issue.name]))[self.issue.name]
		self.assertEqual((state["unread"], state["mentions"]), (1, 1))  # red bubble, not grey

		# Same for a thread they are brought into by the mention.
		frappe.set_user(OWNER)
		thread_id = create_thread(_send(channel_id, "Side topic").name)["thread_id"]
		_send(thread_id, f"{_mention(ASSIGNEE)} over to you")
		frappe.set_user(ASSIGNEE)
		self.assertGreaterEqual(pc.get_issue_chat(self.issue.name)["mentions"], 1)

	def test_mention_in_a_thread_assigns_too(self):
		from raven.api.threads import create_thread

		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		thread_id = create_thread(_send(channel_id, "Side topic").name)["thread_id"]
		_send(thread_id, f"{_mention(LATECOMER)} over to you")
		self.assertIn(LATECOMER, self._assigned())

	def test_mention_in_a_task_chat_assigns_to_the_task(self):
		task = self._task()
		channel_id = pc.ensure_task_chat(task.name)["channel_id"]
		_send(channel_id, f"{_mention(LATECOMER)} please help")
		self.assertIn(LATECOMER, self._assigned("Task", task.name))

	def test_mention_assigns_nobody_who_cannot_read_and_not_the_sender(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		_send(channel_id, f"{_mention(NO_READER)} {_mention(OWNER)} FYI")
		assigned = self._assigned()
		self.assertNotIn(NO_READER, assigned)
		self.assertNotIn(OWNER, assigned)
		self.assertFalse(frappe.db.exists("DocShare", {"share_name": self.issue.name, "user": NO_READER}))

	def test_sender_who_cannot_read_the_record_assigns_nobody_and_sees_no_error(self):
		# A member whose read access went away (role removed) can still post in the chat.
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		issue_chat._ensure_members(frappe._dict(name=channel_id, workspace=WORKSPACE), [NO_READER])
		frappe.set_user(NO_READER)
		frappe.local.message_log = []
		_send(channel_id, f"{_mention(LATECOMER)} please look")
		frappe.set_user(OWNER)
		self.assertNotIn(LATECOMER, self._assigned())
		self.assertEqual(frappe.local.message_log, [])
		# Nor does the mention bring them into the chat (#1794).
		self.assertNotIn(LATECOMER, _members(channel_id))

	def test_keeping_a_mention_unread_never_blocks_the_message(self):
		channel_id = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		with patch("phamos.api.issue_chat.get_datetime", side_effect=Exception("boom")):
			message = _send(channel_id, f"{_mention(LATECOMER)} still sent")
		self.assertTrue(frappe.db.exists("Raven Message", message.name))
		self.assertIn(LATECOMER, self._assigned())

	def test_chat_states_refuse_more_than_a_list_shows(self):
		names = [f"ISS-NOPE-{i}" for i in range(issue_chat.MAX_STATE_NAMES + 1)]
		with self.assertRaises(frappe.ValidationError):
			pc.get_issue_chat_states(frappe.as_json(names))

	def test_chat_states_leave_out_records_the_user_cannot_read(self):
		pc.ensure_issue_chat(self.issue.name)
		frappe.set_user(NO_READER)  # no read on Issue at all: refused, nothing about the chat leaks
		with self.assertRaises(frappe.PermissionError):
			issue_chat.get_chat_states("Issue", [self.issue.name])

	def test_channel_link_is_indexed_after_migrate(self):
		issue_chat.add_raven_indexes()
		columns = {
			row.Column_name
			for row in frappe.db.sql("show index from `tabRaven Channel`", as_dict=True)
		}
		self.assertTrue({"linked_doctype", "linked_document"} <= columns)

	def test_starting_twice_gives_one_chat(self):
		first = pc.ensure_issue_chat(self.issue.name)["channel_id"]
		frappe.set_user(ASSIGNEE)
		self.assertEqual(pc.ensure_issue_chat(self.issue.name)["channel_id"], first)
		self.assertEqual(
			frappe.db.count("Raven Channel", {"linked_doctype": "Issue", "linked_document": self.issue.name}),
			1,
		)

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



	def test_raven_links_open_the_matching_cockpit(self):
		self.assertEqual(
			issue_chat.document_link("Issue", self.issue.name),
			f"/personal-cockpit/issues/list/{self.issue.name}",
		)
		self.assertIsNone(issue_chat.document_link("ToDo", "TODO-0001"))
		task = self._task()
		self.assertEqual(
			issue_chat.document_link("Task", task.name), f"/personal-cockpit/tasks/gantt/{task.name}"
		)

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
		frappe.db.set_value("Task", task.name, "department", department[0])
		self.assertEqual(
			issue_chat.document_link("Task", task.name), f"/sales-cockpit/tasks/gantt/{task.name}"
		)

	def test_task_chat_starts_with_owner_and_assignees(self):
		task = self._task()
		self.assertIsNone(pc.get_task_chat(task.name)["channel_id"])

		state = pc.ensure_task_chat(task.name)
		channel = frappe.get_doc("Raven Channel", state["channel_id"])
		self.assertEqual((channel.linked_doctype, channel.linked_document), ("Task", task.name))
		self.assertEqual(channel.type, "Private")
		self.assertEqual(_members(channel.name), {OWNER, ASSIGNEE})
		self.assertTrue(state["is_member"])
		self.assertEqual(pc.ensure_task_chat(task.name)["channel_id"], channel.name)  # idempotent

		# A new assignee of the Task joins its chat, like on an Issue.
		self._assign(LATECOMER, "Task", task.name)
		self.assertIn(LATECOMER, _members(channel.name))

	def test_task_owner_joins_a_task_chat(self):
		task = self._task(custom_task_owner=LATECOMER)
		channel_id = pc.ensure_task_chat(task.name)["channel_id"]
		self.assertEqual(_members(channel_id), {OWNER, ASSIGNEE, LATECOMER})

	def test_template_task_gets_no_chat(self):
		task = frappe.get_doc({"doctype": "Task", "subject": "Template chat test", "is_template": 1}).insert()
		with self.assertRaises(frappe.ValidationError):
			issue_chat.ensure_chat(task)
		self.assertIsNone(issue_chat.find_channel("Task", task.name))

	def test_task_from_an_issue_says_so_in_its_intro(self):
		task = self._task(issue=self.issue.name)
		channel_id = pc.ensure_task_chat(task.name)["channel_id"]
		intro = frappe.get_all(
			"Raven Message",
			filters={"channel_id": channel_id, "message_type": ("!=", "System")},
			pluck="text",
		)
		self.assertEqual(len(intro), 1)
		self.assertIn(self.issue.name, intro[0])

	def test_completing_a_task_archives_its_chat_and_reopening_restores_it(self):
		task = self._task()
		channel_id = pc.ensure_task_chat(task.name)["channel_id"]

		task.reload()
		task.status = "Working"
		task.save()
		self.assertFalse(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))

		task.reload()
		task.status = "Completed"
		task.save()
		self.assertTrue(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))
		self.assertEqual(pc.ensure_task_chat(task.name)["channel_id"], channel_id)  # no second chat

		task.reload()
		task.status = "Open"
		task.save()
		self.assertFalse(frappe.db.get_value("Raven Channel", channel_id, "is_archived"))
		lines = _system_lines(channel_id)
		for status in ("Working", "Completed", "Open"):
			self.assertTrue(any(f"set the status to {status}" in line for line in lines), status)

	def test_task_out_of_scope_gets_no_chat(self):
		task = self._task()
		frappe.set_user(LATECOMER)  # neither owner nor assignee: not in the Personal Cockpit
		with self.assertRaises(frappe.ValidationError):
			pc.get_task_chat(task.name)
		with self.assertRaises(frappe.ValidationError):
			pc.ensure_task_chat(task.name)

	def test_every_cockpit_exposes_the_chat_endpoints(self):
		endpoints = (
			"get_issue_chat",
			"ensure_issue_chat",
			"get_issue_chat_states",
			"get_task_chat",
			"ensure_task_chat",
		)
		modules = (
			pc,
			sales_spa,
			human_resources_spa,
			accounting_spa,
			project_management_spa,
			software_development_spa,
		)
		for module in modules:
			for name in endpoints:
				self.assertIn(getattr(module, name), frappe.whitelisted, f"{module.__name__}.{name}")

	# Ideas up for vote (#1842)

	def _idea(self):
		"""An idea of OWNER, handed in for a vote."""
		idea = pc.create_idea("Idea chat test", content="<p>Let's talk</p>")
		return pc.hand_in_idea_for_vote(idea["name"])

	def test_idea_chat_opens_only_while_up_for_vote(self):
		idea = pc.create_idea("Private idea")
		with self.assertRaises(frappe.ValidationError):
			pc.ensure_idea_chat(idea["name"])
		pc.hand_in_idea_for_vote(idea["name"])

		state = pc.ensure_idea_chat(idea["name"])
		channel = frappe.db.get_value(
			"Raven Channel", state["channel_id"], ["type", "linked_doctype", "linked_document"], as_dict=True
		)
		self.assertEqual((channel.type, channel.linked_doctype, channel.linked_document), ("Private", "Idea", idea["name"]))
		self.assertEqual(_members(state["channel_id"]), {OWNER})
		intro = frappe.get_all(
			"Raven Message",
			{"channel_id": state["channel_id"], "message_type": "Text"},
			["text", "link_doctype"],
		)[0]
		self.assertIn("Chat about the idea Private idea", intro.text)
		# A plain link, not Raven's document card: that fails for colleagues and names the author.
		self.assertFalse(intro.link_doctype)
		self.assertIn(f'href="/personal-cockpit/ideas/vote/{idea["name"]}"', intro.text)

	def test_author_joins_a_colleagues_idea_chat_only_while_authors_are_shown(self):
		frappe.db.set_single_value("phamos Settings", "personal_ideas_show_author", 1)
		shown = self._idea()
		frappe.set_user(LATECOMER)
		self.assertEqual(_members(pc.ensure_idea_chat(shown["name"])["channel_id"]), {LATECOMER, OWNER})

		frappe.set_user(OWNER)
		frappe.db.set_single_value("phamos Settings", "personal_ideas_show_author", 0)
		hidden = self._idea()
		frappe.set_user(LATECOMER)
		channel_id = pc.ensure_idea_chat(hidden["name"])["channel_id"]
		self.assertEqual(_members(channel_id), {LATECOMER})
		# The author can still join on their own.
		frappe.set_user(OWNER)
		pc.ensure_idea_chat(hidden["name"])
		self.assertEqual(_members(channel_id), {LATECOMER, OWNER})

	def test_colleague_joins_the_chat_of_an_idea_up_for_vote(self):
		idea = self._idea()
		channel_id = pc.ensure_idea_chat(idea["name"])["channel_id"]
		frappe.set_user(LATECOMER)
		state = pc.get_idea_chat(idea["name"])
		self.assertEqual((state["channel_id"], state["is_member"]), (channel_id, False))
		self.assertTrue(pc.ensure_idea_chat(idea["name"])["is_member"])
		self.assertIn(LATECOMER, _members(channel_id))

	def test_nobody_else_reaches_the_chat_of_a_private_idea(self):
		idea = pc.create_idea("Still private")
		frappe.set_user(LATECOMER)
		for call in (pc.get_idea_chat, pc.ensure_idea_chat):
			with self.assertRaises(frappe.PermissionError):
				call(idea["name"])

	def test_mention_in_an_idea_chat_adds_but_does_not_assign(self):
		idea = self._idea()
		channel_id = pc.ensure_idea_chat(idea["name"])["channel_id"]
		_send(channel_id, f"{_mention(LATECOMER)} what do you think?")
		self.assertIn(LATECOMER, _members(channel_id))
		# An assignment would share the idea and keep it readable after a withdraw.
		self.assertFalse(frappe.db.exists("ToDo", {"reference_type": "Idea", "reference_name": idea["name"]}))
		self.assertFalse(frappe.db.exists("DocShare", {"share_doctype": "Idea", "share_name": idea["name"]}))

	def test_withdraw_archives_the_idea_chat_and_hand_in_restores_it(self):
		idea = self._idea()
		channel_id = pc.ensure_idea_chat(idea["name"])["channel_id"]
		pc.withdraw_idea_from_vote(idea["name"])
		self.assertEqual(frappe.db.get_value("Raven Channel", channel_id, "is_archived"), 1)
		self.assertTrue(any("withdrew the idea" in t for t in _system_lines(channel_id)))
		self.assertTrue(pc.get_idea_chat(idea["name"])["archived"])  # the owner still reads it
		with self.assertRaises(frappe.ValidationError):
			pc.ensure_idea_chat(idea["name"])
		frappe.set_user(LATECOMER)
		with self.assertRaises(frappe.PermissionError):
			pc.get_idea_chat(idea["name"])

		frappe.set_user(OWNER)
		pc.hand_in_idea_for_vote(idea["name"])
		self.assertEqual(frappe.db.get_value("Raven Channel", channel_id, "is_archived"), 0)
		self.assertTrue(any("handed the idea in for a vote again" in t for t in _system_lines(channel_id)))
		self.assertEqual(pc.ensure_idea_chat(idea["name"])["channel_id"], channel_id)

	def test_composting_archives_the_idea_chat(self):
		idea = self._idea()
		channel_id = pc.ensure_idea_chat(idea["name"])["channel_id"]
		pc.update_idea(idea["name"], stage="Compost")
		self.assertEqual(frappe.db.get_value("Raven Channel", channel_id, "is_archived"), 1)

	def test_raven_links_open_the_idea_in_the_vote_list(self):
		idea = self._idea()
		self.assertEqual(
			issue_chat.document_link("Idea", idea["name"]), f"/personal-cockpit/ideas/vote/{idea['name']}"
		)
