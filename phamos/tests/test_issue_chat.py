# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Issue chat (#1614): one Private Raven channel per Issue, members from owner and assignees."""

from unittest import skipUnless
from urllib.parse import quote
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
		self.assertEqual(pc.get_issue_chat(self.issue.name)["unread"], 1)

	def test_dm_carries_the_issue_link_once(self):
		result = pc.start_issue_dm(self.issue.name, ASSIGNEE)
		channel = frappe.get_doc("Raven Channel", result["channel_id"])
		self.assertTrue(channel.is_direct_message)
		self.assertEqual(result["url"], f"/raven/dm-channel/{quote(channel.name, safe='')}")

		pc.start_issue_dm(self.issue.name, ASSIGNEE)
		links = frappe.get_all(
			"Raven Message",
			filters={"channel_id": channel.name, "link_doctype": "Issue", "link_document": self.issue.name},
		)
		self.assertEqual(len(links), 1)

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
		endpoints = ("get_issue_chat", "ensure_issue_chat", "get_issue_chat_states", "start_issue_dm")
		for module in (pc, sales_spa):
			for name in endpoints:
				self.assertIn(getattr(module, name), frappe.whitelisted, f"{module.__name__}.{name}")
