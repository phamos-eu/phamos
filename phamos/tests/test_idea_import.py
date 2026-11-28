# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Import ideas from a NextChapter site (#1776), against a fake NextChapter."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.cockpits.doctype.idea_import import idea_import

ANNA = "nc-anna@example.com"
BEN = "nc-ben@example.com"
FALLBACK = "nc-fallback@example.com"
SITE = "https://next-chapter.example.com"

CHAPTERS = [
	{
		"name": "CHAP-00001",
		"owner": "anna@nextchapter.example",
		"creation": "2026-09-01 10:00:00.000000",
		"modified": "2026-09-05 12:00:00.000000",
		"title": "Weekly idea target",
		"content": "<p>Count ideas per week.</p>",
		"writing_stage": "5",
		"spawned_from": None,
		"last_session_words": 120,
	},
	{
		"name": "CHAP-00002",
		"owner": "anna@nextchapter.example",
		"creation": "2026-09-02 09:00:00.000000",
		"modified": "2026-09-02 09:30:00.000000",
		"title": "Team targets",
		"content": "<p>Also for teams.</p>",
		"writing_stage": "∞",
		"spawned_from": "CHAP-00001",
		"last_session_words": 0,
	},
	{
		"name": "CHAP-00003",
		"owner": "someone@nextchapter.example",
		"creation": "2026-09-03 08:00:00.000000",
		"modified": "2026-09-20 08:00:00.000000",
		"title": "Finished thing",
		"content": "<p>Done.</p>",
		"writing_stage": "Done",
		"spawned_from": None,
		"last_session_words": 0,
	},
]
SESSIONS = [
	{
		"name": "ws1",
		"owner": "anna@nextchapter.example",
		"creation": "2026-09-04 07:30:00.000000",
		"modified": "2026-09-04 07:30:00.000000",
		"chapter": "CHAP-00001",
		"user": "anna@nextchapter.example",
		"started_on": "2026-09-04 07:00:00",
		"ended_on": "2026-09-04 07:25:00",
		"duration_mins": 24.6,
		"words_planned": 300,
		"words_written": 120,
		"aim_choice": "more",
		"felt_productive": "not_really",
	},
]


class FakeNextChapter:
	def get_all(self, doctype, fields):
		rows = CHAPTERS if doctype == idea_import.CHAPTER else SESSIONS
		return [{f: row.get(f) for f in fields} for row in rows]


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


class TestIdeaImport(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for email in (ANNA, BEN, FALLBACK):
			_ensure_user(email)
		fake = patch.object(idea_import, "get_client", return_value=FakeNextChapter())
		fake.start()
		self.addCleanup(fake.stop)
		self.doc = frappe.get_doc(
			{
				"doctype": "Idea Import",
				"source_url": SITE + "/",
				"username": "admin",
				"password": "secret",
				"default_user": FALLBACK,
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _load_and_map(self):
		idea_import.load_accounts(self.doc.name)
		self.doc.reload()
		for row in self.doc.users:
			if row.remote_user == "anna@nextchapter.example":
				row.user = ANNA
		self.doc.save()

	def _idea(self, remote):
		return frappe.get_doc("Idea", {"imported_from": f"next-chapter.example.com/{remote}"})

	def test_load_accounts_counts_ideas_and_sessions(self):
		idea_import.load_accounts(self.doc.name)
		self.doc.reload()
		rows = {row.remote_user: row for row in self.doc.users}
		self.assertEqual(rows["anna@nextchapter.example"].ideas, 2)
		self.assertEqual(rows["anna@nextchapter.example"].sessions, 1)
		self.assertEqual(rows["someone@nextchapter.example"].ideas, 1)
		self.assertIsNone(rows["anna@nextchapter.example"].user)
		self.assertEqual(self.doc.status, "Accounts Loaded")

	def test_import_maps_stage_user_dates_and_links(self):
		self._load_and_map()
		result = idea_import.run_import(self.doc.name)
		self.assertEqual(result, {"ideas_created": 3, "sessions_created": 1, "skipped": 0, "to_default_user": 1})

		first = self._idea("CHAP-00001")
		self.assertEqual((first.user, first.owner, first.stage), (ANNA, ANNA, "Young plant"))
		self.assertEqual(str(first.creation), "2026-09-01 10:00:00")
		self.assertEqual(first.last_session_words, 120)

		child = self._idea("CHAP-00002")
		self.assertEqual(child.stage, "Seed")
		self.assertEqual(child.spawned_from, first.name)

		done = self._idea("CHAP-00003")
		self.assertEqual((done.user, done.stage), (FALLBACK, "Harvest"))
		self.assertTrue(done.harvested_on)

		version = frappe.get_all(
			"Version", filters={"ref_doctype": "Idea", "docname": first.name}, fields=["creation"]
		)
		self.assertEqual([str(v.creation) for v in version], ["2026-09-01 10:00:00"])

	def test_sessions_follow_their_idea(self):
		self._load_and_map()
		idea_import.run_import(self.doc.name)
		session = frappe.get_doc("Idea Writing Session", {"imported_from": "next-chapter.example.com/ws1"})
		self.assertEqual(session.user, ANNA)
		self.assertEqual(session.idea, self._idea("CHAP-00001").name)
		self.assertEqual(
			(session.duration_mins, session.word_goal, session.words_written, session.aim_choice, session.felt_productive),
			(25, 300, 120, "more", "Not really"),
		)

	def test_second_run_creates_nothing(self):
		self._load_and_map()
		idea_import.run_import(self.doc.name)
		again = idea_import.run_import(self.doc.name)
		self.assertEqual(again, {"ideas_created": 0, "sessions_created": 0, "skipped": 3, "to_default_user": 0})
		self.assertEqual(frappe.db.count("Idea", {"imported_from": ("like", "next-chapter.example.com/%")}), 3)

	def test_imported_ideas_are_private_to_their_user(self):
		self._load_and_map()
		idea_import.run_import(self.doc.name)
		_ensure_user(BEN, ("Employee", "System Manager"))
		frappe.set_user(BEN)
		self.assertEqual(frappe.get_list("Idea", filters={"imported_from": ("is", "set")}, pluck="name"), [])

	def test_only_system_managers_may_import(self):
		frappe.set_user(BEN)
		with self.assertRaises(frappe.PermissionError):
			idea_import.run_import(self.doc.name)

	def test_a_failure_undoes_the_partial_import(self):
		self._load_and_map()
		real = idea_import._set_dates
		calls = []

		def fail_on_second(*args, **kwargs):
			calls.append(args)
			if len(calls) == 2:
				raise frappe.ValidationError("boom")
			return real(*args, **kwargs)

		with patch.object(idea_import, "_set_dates", side_effect=fail_on_second):
			result = idea_import.run_import(self.doc.name)
		self.assertEqual(result, {"failed": True})
		self.assertEqual(frappe.db.count("Idea", {"imported_from": ("like", "next-chapter.example.com/%")}), 0)
		self.doc.reload()
		self.assertEqual(self.doc.status, "Failed")
		self.assertIn("boom", self.doc.log)

	def test_site_must_be_a_web_address(self):
		self.doc.source_url = "next-chapter.example.com"
		with self.assertRaises(frappe.ValidationError):
			self.doc.save()
		self.assertEqual(frappe.get_doc("Idea Import", self.doc.name).source_url, SITE)
