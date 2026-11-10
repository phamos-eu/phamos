# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Hand in an idea for a vote (phamos/phamos#1842), with users who are not Administrator."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from phamos.api import personal_cockpit as pc
from phamos.api import personal_ideas as ideas

USER = "idea-vote-a@example.com"
OTHER = "idea-vote-b@example.com"  # System Manager
THIRD = "idea-vote-c@example.com"
SETTING = "personal_ideas_show_author"


def _ensure_user(email, roles=("Employee",)):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	missing = set(roles) - set(frappe.get_roles(email))
	if missing:
		frappe.get_doc("User", email).add_roles(*missing)


def _as(user, fn, *args, **kwargs):
	previous = frappe.session.user
	frappe.set_user(user)
	try:
		return fn(*args, **kwargs)
	finally:
		frappe.set_user(previous)


class TestIdeaVotes(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		_ensure_user(USER)
		_ensure_user(OTHER, ("Employee", "System Manager"))
		_ensure_user(THIRD)
		self.now = now_datetime()
		clock = patch.object(ideas, "now_datetime", side_effect=lambda: self.now)
		clock.start()
		self.addCleanup(clock.stop)
		frappe.set_user(USER)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def _later(self, minutes):
		self.now = self.now + timedelta(minutes=minutes)

	def _vote_row(self, user, name):
		return next(row for row in _as(user, pc.get_ideas_for_vote) if row["name"] == name)

	def _handed_in(self, title="Shared", content="<p>For all</p>"):
		idea = pc.create_idea(title, content=content)
		return pc.hand_in_idea_for_vote(idea["name"])

	# hand in

	def test_hand_in_opens_the_idea_and_stamps_the_time(self):
		idea = pc.create_idea("Shared")
		self.assertEqual(idea["vote_status"], "")
		handed = pc.hand_in_idea_for_vote(idea["name"])
		self.assertEqual(handed["vote_status"], "Open for vote")
		self.assertEqual(handed["vote_count"], 0)
		self.assertTrue(handed["handed_in_on"])

	def test_hand_in_makes_the_idea_readable_for_others(self):
		idea = self._handed_in()
		private = pc.create_idea("Still mine")

		frappe.set_user(OTHER)
		visible = frappe.get_list("Idea", pluck="name")
		self.assertIn(idea["name"], visible)
		self.assertNotIn(private["name"], visible)
		self.assertTrue(frappe.has_permission("Idea", "read", doc=idea["name"]))
		self.assertFalse(frappe.has_permission("Idea", "write", doc=idea["name"]))
		self.assertFalse(frappe.has_permission("Idea", "read", doc=private["name"]))
		rows = {row["name"]: row for row in pc.get_ideas_for_vote()}
		self.assertNotIn(private["name"], rows)
		self.assertFalse(rows[idea["name"]]["mine"])
		self.assertEqual(pc.get_idea_for_vote(idea["name"])["content"], "<p>For all</p>")
		# My Ideas and the owner's Idea page stay the owner's.
		self.assertNotIn(idea["name"], [row["name"] for row in pc.get_ideas(include_closed=1)])
		with self.assertRaises(frappe.PermissionError):
			pc.get_idea(idea["name"])
		with self.assertRaises(frappe.PermissionError):
			pc.update_idea(idea["name"], title="Hijacked")
		with self.assertRaises(frappe.PermissionError):
			pc.get_idea_for_vote(private["name"])

	def test_history_and_sessions_stay_private_after_hand_in(self):
		idea = pc.create_idea("Shared", content="<p>draft</p>")
		pc.complete_idea_writing_session(idea["name"], str(add_to_date(self.now, minutes=-5)), 10, 300, "similar")
		pc.hand_in_idea_for_vote(idea["name"])

		frappe.set_user(OTHER)
		self.assertEqual(frappe.get_list("Idea Writing Session", pluck="name"), [])
		self.assertEqual(
			frappe.get_list("Version", filters={"ref_doctype": "Idea", "docname": idea["name"]}, pluck="name"), []
		)
		self.assertNotIn("children", pc.get_idea_for_vote(idea["name"]))

	def test_hand_in_is_idempotent_and_writes_no_version(self):
		idea = pc.create_idea("Once")
		before = frappe.db.count("Version", {"ref_doctype": "Idea", "docname": idea["name"]})
		first = pc.hand_in_idea_for_vote(idea["name"])
		self._later(5)
		second = pc.hand_in_idea_for_vote(idea["name"])
		self.assertEqual(first["handed_in_on"], second["handed_in_on"])
		self.assertEqual(frappe.db.count("Version", {"ref_doctype": "Idea", "docname": idea["name"]}), before)

	def test_composted_idea_cannot_be_handed_in(self):
		idea = pc.create_idea("Old")
		pc.update_idea(idea["name"], stage="Compost")
		with self.assertRaises(frappe.ValidationError):
			pc.hand_in_idea_for_vote(idea["name"])

	def test_only_the_owner_hands_in_and_withdraws(self):
		idea = pc.create_idea("Mine")
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			pc.hand_in_idea_for_vote(idea["name"])
		frappe.set_user(USER)
		pc.hand_in_idea_for_vote(idea["name"])
		frappe.set_user(OTHER)
		with self.assertRaises(frappe.PermissionError):
			pc.withdraw_idea_from_vote(idea["name"])

	def test_website_users_see_no_ideas_up_for_vote(self):
		idea = self._handed_in()
		frappe.set_user("Administrator")
		portal = "idea-vote-portal@example.com"
		if not frappe.db.exists("User", portal):
			frappe.get_doc(
				{"doctype": "User", "email": portal, "first_name": "portal", "user_type": "Website User", "send_welcome_email": 0}
			).insert(ignore_permissions=True)
		frappe.set_user(portal)
		for call in (pc.get_ideas_for_vote, lambda: pc.get_idea_for_vote(idea["name"]), lambda: pc.vote_idea(idea["name"])):
			with self.assertRaises(frappe.PermissionError):
				call()

	# votes

	def test_vote_toggles_and_counts(self):
		idea = self._handed_in()
		modified = frappe.db.get_value("Idea", idea["name"], "modified")

		self.assertEqual(_as(OTHER, pc.vote_idea, idea["name"]), {"name": idea["name"], "voted": True, "vote_count": 1})
		self.assertEqual(_as(OTHER, pc.vote_idea, idea["name"])["vote_count"], 0)
		_as(OTHER, pc.vote_idea, idea["name"])
		result = _as(THIRD, pc.vote_idea, idea["name"])
		self.assertEqual(result, {"name": idea["name"], "voted": True, "vote_count": 2})
		self.assertEqual(frappe.db.get_value("Idea", idea["name"], "vote_count"), 2)
		# A vote does not touch `modified`, so the owner's autosave keeps working.
		self.assertEqual(frappe.db.get_value("Idea", idea["name"], "modified"), modified)
		self.assertEqual(pc.get_idea(idea["name"])["vote_count"], 2)

		row = self._vote_row(OTHER, idea["name"])
		self.assertTrue(row["voted"])
		self.assertEqual(row["vote_count"], 2)

	def test_list_is_ordered_by_votes(self):
		few = self._handed_in("Few")
		self._later(1)
		many = self._handed_in("Many")
		self._later(1)
		none = self._handed_in("None yet")
		_as(OTHER, pc.vote_idea, many["name"])
		_as(THIRD, pc.vote_idea, many["name"])
		_as(OTHER, pc.vote_idea, few["name"])
		mine = {few["name"], many["name"], none["name"]}
		names = [row["name"] for row in _as(THIRD, pc.get_ideas_for_vote) if row["name"] in mine]
		self.assertEqual(names, [many["name"], few["name"], none["name"]])

	def test_owner_cannot_vote_for_own_idea(self):
		idea = self._handed_in()
		with self.assertRaises(frappe.PermissionError):
			pc.vote_idea(idea["name"])
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Idea Vote", "idea": idea["name"], "user": USER}).insert(ignore_permissions=True)
		row = self._vote_row(USER, idea["name"])
		self.assertTrue(row["mine"])
		self.assertFalse(row["voted"])

	def test_vote_on_idea_not_open_is_refused(self):
		idea = pc.create_idea("Private")
		with self.assertRaises(frappe.PermissionError):
			_as(OTHER, pc.vote_idea, idea["name"])
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Idea Vote", "idea": idea["name"], "user": OTHER}).insert(ignore_permissions=True)

	def test_one_vote_per_user_and_idea(self):
		idea = self._handed_in()
		_as(OTHER, pc.vote_idea, idea["name"])
		with self.assertRaises(frappe.UniqueValidationError):
			frappe.get_doc({"doctype": "Idea Vote", "idea": idea["name"], "user": OTHER}).insert(ignore_permissions=True)

	def test_votes_are_private(self):
		idea = self._handed_in()
		_as(OTHER, pc.vote_idea, idea["name"])
		_as(THIRD, pc.vote_idea, idea["name"])
		mine = {"idea": idea["name"]}
		self.assertEqual(_as(OTHER, frappe.get_list, "Idea Vote", filters=mine, pluck="user"), [OTHER])
		with self.assertRaises(frappe.PermissionError):  # no role on Idea Vote: the API is the way in
			frappe.get_list("Idea Vote", filters=mine)
		self.assertEqual(len(_as("Administrator", frappe.get_list, "Idea Vote", filters=mine)), 2)

	# withdraw

	def test_withdraw_hides_the_idea_and_removes_its_votes(self):
		idea = self._handed_in()
		_as(OTHER, pc.vote_idea, idea["name"])
		withdrawn = pc.withdraw_idea_from_vote(idea["name"])
		self.assertEqual(withdrawn["vote_status"], "")
		self.assertEqual(withdrawn["vote_count"], 0)
		self.assertIsNone(withdrawn["handed_in_on"])
		self.assertEqual(frappe.db.count("Idea Vote", {"idea": idea["name"]}), 0)
		frappe.set_user(OTHER)
		self.assertNotIn(idea["name"], frappe.get_list("Idea", pluck="name"))
		self.assertNotIn(idea["name"], [row["name"] for row in pc.get_ideas_for_vote()])
		with self.assertRaises(frappe.PermissionError):
			pc.vote_idea(idea["name"])

	def test_compost_withdraws_from_the_vote(self):
		idea = self._handed_in()
		_as(OTHER, pc.vote_idea, idea["name"])
		composted = pc.update_idea(idea["name"], stage="Compost")
		self.assertEqual(composted["vote_status"], "")
		self.assertEqual(composted["vote_count"], 0)
		self.assertEqual(frappe.db.count("Idea Vote", {"idea": idea["name"]}), 0)
		again = pc.update_idea(idea["name"], stage="Seed")
		self.assertEqual(again["vote_status"], "")  # taking it up again does not hand it in

	def test_deleting_the_idea_deletes_its_votes(self):
		idea = self._handed_in()
		_as(OTHER, pc.vote_idea, idea["name"])
		frappe.set_user("Administrator")
		frappe.delete_doc("Idea", idea["name"], force=True)
		self.assertEqual(frappe.db.count("Idea Vote", {"idea": idea["name"]}), 0)

	# author setting

	def test_author_follows_the_setting(self):
		idea = self._handed_in()
		frappe.db.set_single_value("phamos Settings", SETTING, 1)
		row = self._vote_row(OTHER, idea["name"])
		self.assertEqual(row["author"]["name"], USER)
		self.assertEqual(row["author"]["full_name"], "idea-vote-a")
		self.assertNotIn("user", row)

		frappe.db.set_single_value("phamos Settings", SETTING, 0)
		row = self._vote_row(OTHER, idea["name"])
		self.assertIsNone(row["author"])
		self.assertNotIn("user", row)
		self.assertIsNone(_as(OTHER, pc.get_idea_for_vote, idea["name"])["author"])

	def test_patch_turns_the_author_on_where_nothing_is_stored(self):
		from phamos.patches.v1_0 import set_personal_ideas_show_author_default as patch_module

		def show_author():
			frappe.db.value_cache.pop("phamos Settings", None)
			return ideas.show_author()

		frappe.db.delete("Singles", {"doctype": "phamos Settings", "field": SETTING})
		self.assertFalse(show_author())  # what Frappe reads for a Check with no stored value
		patch_module.execute()
		self.assertTrue(show_author())
		# A choice already made stays.
		frappe.db.set_single_value("phamos Settings", SETTING, 0)
		patch_module.execute()
		self.assertFalse(show_author())
