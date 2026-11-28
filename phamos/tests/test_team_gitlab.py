# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Team Cockpit GitLab and SLA statistics (#1976): items count by the team's people."""

from datetime import date
from unittest.mock import patch

import frappe

from phamos.api import team_cockpit
from phamos.cockpits import team_gitlab, teams
from phamos.tests.test_team_assignment import TEAM_A, TeamAssignmentTestCase

TODAY = date(2026, 3, 31)
PROJECTS = ("_Test GitLab Own", "_Test GitLab Other", "_Test GitLab Internal")


class TeamGitlabTestCase(TeamAssignmentTestCase):
	def setUp(self):
		super().setUp()
		for project in PROJECTS:
			if not frappe.db.exists("GitLab Project", project):
				frappe.get_doc({"doctype": "GitLab Project", "name": project, "title": project, "project_id": project}).insert(
					ignore_permissions=True, set_name=project
				)
		groups = patch.object(
			team_gitlab,
			"_project_groups",
			return_value=(dict(zip(PROJECTS, team_gitlab.GROUPS)), {PROJECTS[0]}),
		)
		groups.start()
		self.addCleanup(groups.stop)
		self.anna_email = frappe.db.get_value("Employee", self.anna, "user_id")
		self.ben_email = frappe.db.get_value("Employee", self.ben, "user_id")

	def item(self, email, created, closed=None, project=PROJECTS[0], parent=None, comments=0):
		doc = frappe.get_doc(
			{
				"doctype": "GitLab Issue",
				"title": "Test item",
				"issue_id": frappe.generate_hash(length=8),
				"state": "closed" if closed else "opened",
				"created_at": created,
				"closed_at": closed,
				"assignee_email": email,
				"gitlab_project": project,
				"parent_issue": parent,
				"comments": [{"note_id": frappe.generate_hash(length=10), "author": "x", "comment": "c"} for _ in range(comments)],
			}
		)
		doc.flags.ignore_links = True
		return doc.insert(ignore_permissions=True).name

	def stats(self):
		return team_gitlab.team_gitlab_statistics(TEAM_A, today=TODAY)


class TestWhichItemsCount(TeamGitlabTestCase):
	def test_by_assignee_email_and_membership_on_the_date(self):
		self.assign(self.anna, TEAM_A, "2026-03-01")
		# closed before anna joined: not the team's
		self.item(self.anna_email, "2026-02-01 09:00:00", "2026-02-20 09:00:00")
		# opened before, closed after joining: closed counts, opened not
		self.item(self.anna_email, "2026-02-25 09:00:00", "2026-03-10 09:00:00")
		# ben is not in the team
		self.item(self.ben_email, "2026-03-02 09:00:00", "2026-03-05 09:00:00")
		current = self.stats().windows["current"]
		self.assertEqual((current.closed_total, current.opened_total), (1, 0))

	def test_items_count_wherever_the_person_works(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		for project in PROJECTS:
			self.item(self.anna_email.upper(), "2026-03-02 09:00:00", "2026-03-04 09:00:00", project=project)
		current = self.stats().windows["current"]
		self.assertEqual(current.closed, {"own": 1, "other": 1, "internal": 1})

	def test_unmatched_assignees_in_own_projects_are_only_counted_in_the_notice(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		self.item("stranger@example.com", "2026-03-02 09:00:00")
		self.item(None, "2026-03-02 09:00:00")
		# an employee of another team is known, not "unmatched"
		self.item(self.ben_email, "2026-03-02 09:00:00")
		# unmatched outside the team's own projects: not the team's concern
		self.item("stranger@example.com", "2026-03-02 09:00:00", project=PROJECTS[1])
		data = self.stats()
		# only the stranger in the own project: unassigned items are no matching problem
		self.assertEqual(data.unmatched_own_items, 1)
		self.assertEqual(data.open_items.count, 0)

	def test_dates_are_taken_in_the_system_time_zone(self):
		self.assign(self.anna, TEAM_A, "2026-03-01")
		# stored as UTC: 28 Feb 23:30 UTC is 1 March 00:30 in Berlin, the day anna joined
		self.item(self.anna_email, "2026-02-20 09:00:00", "2026-02-28 23:30:00")
		with patch.object(team_gitlab, "get_system_timezone", return_value="Europe/Berlin"):
			self.assertEqual(self.stats().windows["current"].closed_total, 1)
		with patch.object(team_gitlab, "get_system_timezone", return_value="UTC"):
			self.assertEqual(self.stats().windows["current"].closed_total, 0)

	def test_an_open_item_from_before_the_range_is_open_not_opened(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		self.item(self.anna_email, "2024-05-01 09:00:00")
		data = self.stats()
		self.assertEqual((data.open_items.count, data.windows["current"].opened_total), (1, 0))

	def test_a_member_who_leaves_mid_month(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", "2026-03-10")
		self.item(self.anna_email, "2026-03-02 09:00:00", "2026-03-05 09:00:00")
		self.item(self.anna_email, "2026-03-02 09:00:00", "2026-03-15 09:00:00")
		self.assertEqual(self.stats().windows["current"].closed_total, 1)


class TestFigures(TeamGitlabTestCase):
	def test_closing_time_of_work_and_parent_items_and_comments(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		parent = self.item(self.anna_email, "2026-03-01 00:00:00", "2026-03-21 00:00:00", comments=4)
		self.item(self.anna_email, "2026-03-02 00:00:00", "2026-03-04 00:00:00", parent=parent, comments=2)
		self.item(self.anna_email, "2026-03-02 00:00:00", "2026-03-08 00:00:00", comments=0)
		current = self.stats().windows["current"]
		self.assertEqual(current.work_item_days, {"average": 4.0, "median": 4.0, "count": 2})
		self.assertEqual(current.parent_item_days["median"], 20.0)
		self.assertEqual(current.comments_per_closed_item, 2.0)

	def test_open_items_and_their_age(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		self.item(self.anna_email, "2026-03-21 09:00:00")
		self.item(self.anna_email, "2026-03-01 09:00:00")
		open_items = self.stats().open_items
		self.assertEqual((open_items.count, open_items.median_age_days, open_items.oldest_age_days), (2, 20, 30))

	def test_twelve_months_by_group_and_the_previous_month(self):
		self.assign(self.anna, TEAM_A, "2026-01-01")
		self.item(self.anna_email, "2026-02-02 09:00:00", "2026-02-10 09:00:00", project=PROJECTS[1])
		self.item(self.anna_email, "2026-03-02 09:00:00", "2026-03-04 09:00:00")
		data = self.stats()
		months = data.months
		self.assertEqual((months[0].start, months[-1].start, len(months)), (date(2025, 4, 1), date(2026, 3, 1), 12))
		self.assertEqual(months[-2].closed, {"own": 0, "other": 1, "internal": 0})
		self.assertEqual(months[-1].closed, {"own": 1, "other": 0, "internal": 0})
		self.assertEqual(data.windows["previous"].closed_total, 1)


class TestSla(TeamGitlabTestCase):
	def test_hidden_while_tracking_is_off(self):
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 0)
		self.assertIsNone(self.stats().sla)

	def test_figures_of_the_teams_issues(self):
		frappe.db.set_single_value("Support Settings", "track_service_level_agreement", 1)

		def issue(team, responded, response_by, status=None):
			name = frappe.get_doc({"doctype": "Issue", "subject": "SLA test", "custom_team": team}).insert(ignore_permissions=True).name
			frappe.db.set_value(
				"Issue",
				name,
				{
					"first_responded_on": responded,
					"response_by": response_by,
					"first_response_time": 7200,
					"opening_date": "2026-03-02",
					"agreement_status": status,
				},
				update_modified=False,
			)

		issue(TEAM_A, "2026-03-02 10:00:00", "2026-03-02 12:00:00", "Fulfilled")
		issue(TEAM_A, "2026-03-03 10:00:00", "2026-03-03 09:00:00", "Failed")
		issue(None, "2026-03-03 10:00:00", "2026-03-03 09:00:00", "Failed")
		sla = self.stats().sla["current"]
		self.assertEqual((sla.responses, sla.first_response_hours, sla.responses_in_time), (2, 2.0, 50.0))
		self.assertEqual((sla.resolutions, sla.resolutions_in_time), (2, 50.0))


class TestEndpoint(TeamGitlabTestCase):
	def test_the_unmatched_notice_is_not_for_members(self):
		self.assign(self.anna, TEAM_A, "2026-01-01", role="Lead")
		self.assign(self.ben, TEAM_A, "2026-01-01")
		self.item("stranger@example.com", "2026-03-02 09:00:00")
		self.addCleanup(frappe.set_user, "Administrator")
		real = team_gitlab.team_gitlab_statistics
		with patch.object(teams, "require_active_team", return_value=TEAM_A), patch.object(
			team_cockpit, "check_app_permission", return_value=True
		), patch.object(team_gitlab, "team_gitlab_statistics", side_effect=lambda team: real(team, today=TODAY)):
			frappe.set_user(self.ben_email)
			self.assertIsNone(team_cockpit.get_gitlab_statistics().unmatched_own_items)
			frappe.set_user(self.anna_email)
			self.assertEqual(team_cockpit.get_gitlab_statistics().unmatched_own_items, 1)


class TestMergeRequests(TeamGitlabTestCase):
	"""Merge requests (#1977) count like items: by the author's email, member on the merge date."""

	def merge_request(self, email, created, merged=None, project=PROJECTS[0], added=0, removed=0):
		doc = frappe.get_doc(
			{
				"doctype": "GitLab Merge Request",
				"gitlab_project": project,
				"iid": frappe.db.count("GitLab Merge Request") + 1000,
				"title": "Test MR",
				"state": "merged" if merged else "opened",
				"author_email": email,
				"created_at": created,
				"merged_at": merged,
				"lines_added": added,
				"lines_removed": removed,
			}
		)
		doc.flags.ignore_links = True
		return doc.insert(ignore_permissions=True).name

	def test_figures_by_author_and_merge_date(self):
		self.assign(self.anna, TEAM_A, "2026-02-10")
		self.merge_request(self.anna_email, "2026-03-02 09:00:00", "2026-03-04 09:00:00", added=100, removed=20)
		self.merge_request(self.anna_email, "2026-03-05 09:00:00", "2026-03-11 09:00:00", project=PROJECTS[1], added=10, removed=5)
		# merged before anna joined: not the team's
		self.merge_request(self.anna_email, "2026-02-01 09:00:00", "2026-02-05 09:00:00", added=999)
		# another person
		self.merge_request(self.ben_email, "2026-03-02 09:00:00", "2026-03-03 09:00:00", added=50)
		data = self.stats()
		current = data.merge_requests["current"]
		self.assertEqual(current.merged, {"own": 1, "other": 1, "internal": 0})
		self.assertEqual((current.lines_added["own"], current.lines_removed["other"]), (100, 5))
		self.assertEqual(current.days_to_merge, {"average": 4.0, "median": 4.0, "count": 2})
		self.assertEqual(data.months[-1].lines_added, {"own": 100, "other": 10, "internal": 0})
		self.assertEqual(data.months[-2].lines_added, {"own": 0, "other": 0, "internal": 0})
