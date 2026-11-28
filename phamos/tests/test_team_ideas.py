# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Ideas shared with the team (#1980): the same vote, fewer readers."""

from unittest.mock import patch

import frappe

from phamos.api import personal_ideas, team_cockpit
from phamos.cockpits import team_chat, teams
from phamos.cockpits.permissions import can_read_idea
from phamos.tests.test_team_assignment import TEAM_A, TEAM_B, TeamAssignmentTestCase


class TeamIdeasTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		self.anna_a = self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.ben_a = self.assign(self.ben, TEAM_A, "2026-01-01")
		self.cara_b = self.assign(self.cara, TEAM_B, "2026-01-01")
		self.users = {}
		for employee in (self.anna, self.ben, self.cara):
			user = frappe.db.get_value("Employee", employee, "user_id")
			# colleagues are System Users
			frappe.db.set_value("User", user, "user_type", "System User")
			self.users[employee] = user
		self.addCleanup(frappe.set_user, "Administrator")
		for target, value in (("_publish", None), ("_publish_vote", None)):
			p = patch.object(personal_ideas, target, return_value=value)
			p.start()
			self.addCleanup(p.stop)
		p = patch.object(team_cockpit, "check_app_permission", return_value=True)
		p.start()
		self.addCleanup(p.stop)

	def as_user(self, employee):
		frappe.set_user(self.users[employee])

	def shared_idea(self):
		self.as_user(self.ben)
		name = personal_ideas.create_idea(title="Standup at 9:15")["name"]
		personal_ideas.share_idea_with_team(name)
		return name


class TestSharing(TeamIdeasTestCase):
	def test_the_team_reads_and_votes_nobody_else(self):
		name = self.shared_idea()
		self.assertEqual(frappe.db.get_value("Idea", name, ["vote_status", "team"]), ("Open for vote", TEAM_A))
		self.as_user(self.anna)
		self.assertTrue(can_read_idea(name))
		self.assertEqual(personal_ideas.vote_idea(name)["vote_count"], 1)
		self.assertIn(name, [r["name"] for r in personal_ideas.get_ideas_for_vote()])
		self.as_user(self.cara)
		self.assertFalse(can_read_idea(name))
		self.assertNotIn(name, [r["name"] for r in personal_ideas.get_ideas_for_vote()])
		with self.assertRaises(frappe.PermissionError):
			personal_ideas.vote_idea(name)

	def test_opening_to_the_company_keeps_the_votes(self):
		name = self.shared_idea()
		self.as_user(self.anna)
		personal_ideas.vote_idea(name)
		self.as_user(self.ben)
		personal_ideas.hand_in_idea_for_vote(name)
		self.assertEqual(frappe.db.get_value("Idea", name, ["team", "vote_count"]), (None, 1))
		self.as_user(self.cara)
		self.assertTrue(can_read_idea(name))

	def test_withdrawing_removes_the_votes_and_the_team(self):
		name = self.shared_idea()
		self.as_user(self.anna)
		personal_ideas.vote_idea(name)
		self.as_user(self.ben)
		personal_ideas.withdraw_idea_from_vote(name)
		self.assertEqual(frappe.db.get_value("Idea", name, ["vote_status", "team"]), ("", None))
		self.assertEqual(frappe.db.count("Idea Vote", {"idea": name}), 0)

	def test_someone_without_a_team_cannot_share(self):
		self.cara_b.until_date = frappe.utils.add_days(frappe.utils.today(), -1)
		self.cara_b.save()
		self.as_user(self.cara)
		name = personal_ideas.create_idea(title="Lonely")["name"]
		with self.assertRaises(frappe.PermissionError):
			personal_ideas.share_idea_with_team(name)


class TestLeavingTheTeam(TeamIdeasTestCase):
	def test_the_idea_stays_and_can_move(self):
		name = self.shared_idea()
		self.as_user(self.anna)
		personal_ideas.vote_idea(name)
		frappe.set_user("Administrator")
		self.ben_a.until_date = frappe.utils.add_days(frappe.utils.today(), -1)
		self.ben_a.save()
		# stays with the old team, which still reads it
		self.assertEqual(frappe.db.get_value("Idea", name, "team"), TEAM_A)
		self.as_user(self.anna)
		self.assertTrue(can_read_idea(name))
		# the author, now in team B, moves it there; the votes stay
		frappe.set_user("Administrator")
		self.assign(self.ben, TEAM_B, frappe.utils.today())
		self.as_user(self.ben)
		personal_ideas.share_idea_with_team(name)
		self.assertEqual(frappe.db.get_value("Idea", name, ["team", "vote_count"]), (TEAM_B, 1))


class TestTeamCockpit(TeamIdeasTestCase):
	def test_team_ideas_and_a_new_one(self):
		name = self.shared_idea()
		self.as_user(self.anna)
		with patch.object(teams, "require_active_team", return_value=TEAM_A):
			self.assertEqual([r["name"] for r in team_cockpit.get_team_ideas()["ideas"]], [name])
			created = team_cockpit.create_team_idea("Retro every Friday")
		self.assertEqual(frappe.db.get_value("Idea", created["name"], ["user", "team"]), (self.users[self.anna], TEAM_A))
		self.as_user(self.cara)
		with patch.object(teams, "require_active_team", return_value=TEAM_B):
			self.assertEqual(team_cockpit.get_team_ideas()["ideas"], [])

	def test_only_readers_join_a_team_ideas_chat(self):
		name = self.shared_idea()
		values = {
			("Raven Channel", "chan"): ("Idea", name),
			("Raven User", "ru-cara"): (self.users[self.cara], "User"),
			("Raven User", "ru-anna"): (self.users[self.anna], "User"),
		}
		real = frappe.db.get_value

		def get_value(*args, **kwargs):
			doctype = args[0] if args else kwargs.get("doctype")
			key = (doctype, args[1] if len(args) > 1 else kwargs.get("filters"))
			return values.get(key) if isinstance(key[1], str) and key in values else real(*args, **kwargs)

		frappe.set_user("Administrator")
		with patch.object(team_chat.frappe.db, "get_value", side_effect=get_value):
			with self.assertRaises(frappe.PermissionError):
				team_chat.check_channel_member(frappe._dict(channel_id="chan", user_id="ru-cara"))
			team_chat.check_channel_member(frappe._dict(channel_id="chan", user_id="ru-anna"))


class TestReviewFindings(TeamIdeasTestCase):
	def test_moving_takes_the_old_team_out_of_the_chat(self):
		name = self.shared_idea()
		frappe.set_user("Administrator")
		self.ben_a.until_date = frappe.utils.add_days(frappe.utils.today(), -1)
		self.ben_a.save()
		self.assign(self.ben, TEAM_B, frappe.utils.today())
		members = [self.users[self.anna], self.users[self.ben], self.users[self.cara]]
		with patch.object(personal_ideas.issue_chat, "is_raven_installed", return_value=True), patch.object(
			personal_ideas.issue_chat, "find_channel", return_value=frappe._dict(name="chan")
		), patch.object(personal_ideas.issue_chat, "channel_member_users", return_value=members), patch.object(
			personal_ideas.issue_chat, "_remove_members"
		) as remove, patch.object(personal_ideas.issue_chat, "on_idea_vote_change"):
			self.as_user(self.ben)
			personal_ideas.share_idea_with_team(name)
		# anna stays in team A and can no longer read it; ben (author) and cara (team B) stay
		self.assertEqual(remove.call_args.args[1], [self.users[self.anna]])

	def test_the_team_cockpit_shares_with_the_team_on_screen(self):
		frappe.set_user("Administrator")
		with patch.object(teams, "require_active_team", return_value=TEAM_B):
			created = team_cockpit.create_team_idea("From the GM's view")
		self.assertEqual(frappe.db.get_value("Idea", created["name"], "team"), TEAM_B)

	def test_without_a_team_the_personal_cockpit_cannot_share(self):
		frappe.set_user("Administrator")
		name = personal_ideas.create_idea(title="GM idea")["name"]
		with patch.object(teams, "member_teams", return_value=[]), self.assertRaises(frappe.PermissionError):
			personal_ideas.share_idea_with_team(name)

	def test_composting_makes_it_private_again(self):
		name = self.shared_idea()
		doc = frappe.get_doc("Idea", name)
		doc.stage = "Compost"
		doc.flags.ignore_permissions = True
		doc.save()
		self.assertEqual(frappe.db.get_value("Idea", name, ["vote_status", "team"]), ("", None))

	def test_the_owner_cannot_set_the_team_through_the_api(self):
		self.as_user(self.cara)
		name = personal_ideas.create_idea(title="Sneaky")["name"]
		doc = frappe.get_doc("Idea", name)
		doc.team = TEAM_A
		doc.save()
		self.assertIsNone(frappe.db.get_value("Idea", name, "team"))
