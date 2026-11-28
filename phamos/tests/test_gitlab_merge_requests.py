# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab merge request sync (#1977): line counts without generated files, sync range, webhook."""

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import merge_requests as mrs

PROJECT = "_test_mr_project"


def _diff(path, added, removed):
	lines = ["@@ -1,1 +1,1 @@"] + [f"+line {i}" for i in range(added)] + [f"-line {i}" for i in range(removed)]
	return {"new_path": path, "old_path": path, "diff": "\n".join(lines)}


def _mr(iid=7, sha="abc", state="merged"):
	return {
		"iid": iid,
		"title": "Add the thing",
		"web_url": f"https://git.example.com/p/-/merge_requests/{iid}",
		"state": state,
		"author": {"id": 42, "username": "dev"},
		"source_branch": "feat/x",
		"target_branch": "develop",
		"created_at": "2026-03-02T09:00:00.000Z",
		"merged_at": "2026-03-04T15:30:00.000Z" if state == "merged" else None,
		"closed_at": None,
		"sha": sha,
	}


class TestLineCounts(FrappeTestCase):
	def test_generated_files_are_left_out(self):
		patterns = list(mrs.DEFAULT_EXCLUSIONS)
		for path in (
			"yarn.lock",
			"team_frontend/yarn.lock",
			"phamos/public/dist/js/app.bundle.js",
			"phamos/public/team/assets/index-abc.js",
			"spa_shared/lib/vendor.min.js",
			"phamos/public/team/assets/index-abc.js.map",
			"phamos/translations/de.csv",
		):
			self.assertTrue(mrs.is_excluded(path, patterns), path)
		for path in ("phamos/api/team_cockpit.py", "team_frontend/src/views/TeamGitlab.vue", "README.md"):
			self.assertFalse(mrs.is_excluded(path, patterns), path)

	def test_counting(self):
		diffs = [_diff("phamos/api/x.py", 10, 3), _diff("yarn.lock", 500, 400), _diff("phamos/y.py", 2, 0)]
		self.assertEqual(mrs.count_lines(diffs, list(mrs.DEFAULT_EXCLUSIONS)), (12, 3, 2))

	def test_patterns_come_from_gitlab_settings(self):
		with patch.object(mrs.frappe.db, "get_single_value", return_value="docs/*\n\n  *.svg  "):
			self.assertEqual(mrs.exclusion_patterns(), ["docs/*", "*.svg"])
		with patch.object(mrs.frappe.db, "get_single_value", return_value=""):
			self.assertEqual(mrs.exclusion_patterns(), list(mrs.DEFAULT_EXCLUSIONS))


class TestSync(FrappeTestCase):
	def setUp(self):
		self.addCleanup(frappe.db.rollback)
		if not frappe.db.exists("GitLab Project", PROJECT):
			frappe.get_doc({"doctype": "GitLab Project", "title": PROJECT, "project_id": PROJECT}).insert(
				ignore_permissions=True
			)
		for target, value in (("get_user_email", "dev@example.com"), ("_linked_issues", []), ("get_gitlab_headers", {})):
			p = patch.object(mrs, target, return_value=value)
			p.start()
			self.addCleanup(p.stop)

	def test_upsert_counts_lines_once_per_head(self):
		with patch.object(mrs, "_diffs", return_value=[_diff("a.py", 5, 1)]) as diffs:
			name = mrs.upsert_merge_request(PROJECT, _mr(sha="one"))
			mrs.upsert_merge_request(PROJECT, _mr(sha="one"))
			self.assertEqual(diffs.call_count, 1)
			doc = frappe.get_doc("GitLab Merge Request", name)
			self.assertEqual((doc.lines_added, doc.lines_removed, doc.files_changed, doc.author_email), (5, 1, 1, "dev@example.com"))
			# UTC as GitLab sends it
			self.assertEqual(doc.merged_at, datetime(2026, 3, 4, 15, 30))
			diffs.return_value = [_diff("a.py", 9, 2)]
			mrs.upsert_merge_request(PROJECT, _mr(sha="two"))
			self.assertEqual(diffs.call_count, 2)
			self.assertEqual(frappe.db.get_value("GitLab Merge Request", name, "lines_added"), 9)
		self.assertEqual(frappe.db.count("GitLab Merge Request", {"gitlab_project": PROJECT}), 1)

	def test_first_run_fetches_24_months_then_since_the_last_run(self):
		calls = []

		def get_all(path, params=None):
			calls.append(params["updated_after"])
			return [_mr(iid=1)]

		with patch.object(mrs, "_get_all", side_effect=get_all), patch.object(mrs, "_diffs", return_value=[]), patch.object(
			mrs, "now_datetime", return_value=datetime(2026, 11, 28, 12, 0)
		), patch.object(mrs.frappe.db, "commit"):
			mrs.sync_project_merge_requests(PROJECT)
			mrs.sync_project_merge_requests(PROJECT)
		# 24 months before 28 Nov 2026 12:00 system time (Europe/Berlin on the test site: 11:00 UTC)
		self.assertTrue(calls[0].startswith("2024-11-28"))
		self.assertTrue(calls[1].startswith("2026-11-28"))

	def test_webhook_updates_one_merge_request(self):
		class Response:
			def raise_for_status(self):
				pass

			def json(self):
				return _mr(iid=12)

		with patch.object(mrs.requests, "get", return_value=Response()), patch.object(mrs, "_diffs", return_value=[]), patch.object(
			mrs, "_api", return_value="https://git.example.com/api"
		):
			mrs.handle_merge_request_webhook({"project": {"id": PROJECT}, "object_attributes": {"iid": 12}})
		self.assertTrue(frappe.db.exists("GitLab Merge Request", {"gitlab_project": PROJECT, "iid": 12}))

	def test_webhook_of_an_unknown_project_is_ignored(self):
		with patch.object(mrs.requests, "get") as get:
			mrs.handle_merge_request_webhook({"project": {"id": "nope"}, "object_attributes": {"iid": 1}})
		get.assert_not_called()
