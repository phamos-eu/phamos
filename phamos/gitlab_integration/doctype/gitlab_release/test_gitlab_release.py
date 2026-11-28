# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""GitLab Release sync and issue time estimates (#1985), with the GitLab API mocked."""

import random
from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import gitlab_utils
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation


def make_project(implementation=None):
	project_id = str(random.randint(10**8, 10**9))
	frappe.get_doc(
		{
			"doctype": "GitLab Project",
			"project_id": project_id,
			"title": f"_Test Release {project_id}",
			"implementation": implementation,
		}
	).insert(ignore_permissions=True)
	return project_id


def release_payload(tag, milestone_ids=(), upcoming=False, name=None):
	return {
		"tag_name": tag,
		"name": name or f"Release {tag}",
		"description": "Notes",
		"released_at": "2026-11-20T10:00:00.000Z",
		"upcoming_release": upcoming,
		"milestones": [{"id": mid} for mid in milestone_ids],
		"_links": {"self": f"https://git.example.com/releases/{tag}"},
	}


class TestGitLabRelease(FrappeTestCase):
	def setUp(self):
		self.project = make_project(make_implementation().name)
		self.milestone_id = random.randint(10**8, 10**9)
		milestone = frappe.new_doc("GitLab Milestones")
		milestone.update({"title": "Sprint", "milestone_id": self.milestone_id, "gitlab_project": self.project})
		milestone.insert(ignore_permissions=True)
		self.milestone = milestone.name

	def sync(self, releases):
		# releases only for this test's project, and no commit: the sync commits, which would
		# keep test records and touch real projects on the site
		with mock.patch.object(
			gitlab_utils, "get_releases_for_project", side_effect=lambda pid: releases if pid == self.project else []
		), mock.patch.object(frappe.db, "commit"):
			gitlab_utils.sync_gitlab_releases()

	def test_creates_and_updates_by_tag(self):
		self.sync([release_payload("v1.0", [self.milestone_id], upcoming=True)])
		name = f"{self.project}-v1.0"
		release = frappe.get_doc("GitLab Release", name)
		self.assertEqual((release.title, release.upcoming), ("Release v1.0", 1))
		self.assertEqual([row.gitlab_milestone for row in release.milestones], [self.milestone])
		self.assertEqual(release.web_url, "https://git.example.com/releases/v1.0")
		self.assertEqual(str(release.released_at), "2026-11-20 10:00:00")

		# same tag again: updated, not duplicated; milestones follow GitLab
		self.sync([release_payload("v1.0", [], name="Renamed")])
		self.assertEqual(frappe.db.count("GitLab Release", {"gitlab_project": self.project}), 1)
		release.reload()
		self.assertEqual((release.title, release.upcoming, len(release.milestones)), ("Renamed", 0, 0))

	def test_projects_without_implementation_are_skipped(self):
		other = make_project()
		calls = []
		with mock.patch.object(
			gitlab_utils, "get_releases_for_project", side_effect=lambda pid: calls.append(pid) or []
		), mock.patch.object(frappe.db, "commit"):
			gitlab_utils.sync_gitlab_releases()
		self.assertIn(self.project, calls)
		self.assertNotIn(other, calls)

	def test_issue_time_fields_from_rest_and_webhook(self):
		rest = {"time_stats": {"time_estimate": 5400, "total_time_spent": 1800}}
		self.assertEqual(
			gitlab_utils._get_issue_time_fields(rest), {"time_estimate_hours": 1.5, "time_spent_hours": 0.5}
		)
		webhook = {"time_estimate": 7200, "total_time_spent": 0}
		self.assertEqual(
			gitlab_utils._get_issue_time_fields(webhook), {"time_estimate_hours": 2.0, "time_spent_hours": 0.0}
		)
		# no time tracking in the payload: nothing to overwrite
		self.assertEqual(gitlab_utils._get_issue_time_fields({"title": "x"}), {})

	def test_one_broken_release_does_not_undo_the_others(self):
		broken = release_payload("v2.0")
		del broken["tag_name"]
		with mock.patch.object(frappe, "log_error") as log_error:
			self.sync([release_payload("v1.0"), broken, release_payload("v3.0")])
		log_error.assert_called_once()
		self.assertTrue(frappe.db.exists("GitLab Release", f"{self.project}-v1.0"))
		self.assertTrue(frappe.db.exists("GitLab Release", f"{self.project}-v3.0"))

	def test_an_unreachable_project_does_not_stop_the_others(self):
		other = make_project(make_implementation().name)

		def fetch(project_id):
			if project_id == other:
				raise frappe.ValidationError("GitLab answered 404")
			return [release_payload("v1.0")] if project_id == self.project else []

		with mock.patch.object(gitlab_utils, "get_releases_for_project", side_effect=fetch), mock.patch.object(
			frappe.db, "commit"
		), mock.patch.object(frappe, "log_error") as log_error:
			gitlab_utils.sync_gitlab_releases()
		self.assertTrue(frappe.db.exists("GitLab Release", f"{self.project}-v1.0"))
		self.assertTrue(any(other in str(call) for call in log_error.call_args_list))

	def test_a_non_200_answer_is_an_error_not_an_empty_list(self):
		response = mock.Mock(status_code=403)
		settings = frappe._dict(gitlab_url="https://git.example.com")
		with mock.patch.object(gitlab_utils.requests, "get", return_value=response), mock.patch.object(
			frappe, "get_single", return_value=settings
		), mock.patch.object(gitlab_utils, "get_gitlab_headers", return_value={}):
			self.assertRaises(frappe.ValidationError, gitlab_utils.get_releases_for_project, "1")
