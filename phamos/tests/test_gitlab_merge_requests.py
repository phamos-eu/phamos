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


def _mr(iid=7, sha="abc", state="merged", updated="2026-03-04T15:30:00.000Z"):
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
		"updated_at": updated,
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

	def test_code_lines_that_look_like_headers_count(self):
		# GitLab's per-file diff has no "+++"/"---" headers: these are code lines
		diff = {"new_path": "a.sql", "diff": "@@ -1,2 +1,2 @@\n--- old yaml marker\n-- removed comment\n+++i;\n+---\n \\ No newline"}
		self.assertEqual(mrs.count_lines([diff], []), (2, 2, 1))

	def test_a_folder_pattern(self):
		self.assertTrue(mrs.is_excluded("docs/guide/intro.md", ["docs/"]))
		self.assertFalse(mrs.is_excluded("phamos/docs.py", ["docs/"]))

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

	def test_first_run_fetches_24_months_then_from_the_last_update(self):
		calls = []

		def get_all(path, params=None):
			calls.append(params)
			return [_mr(iid=1, updated="2026-11-20T10:00:00.000Z")]

		with patch.object(mrs, "_get_all", side_effect=get_all), patch.object(mrs, "_diffs", return_value=[]), patch.object(
			mrs, "now_datetime", return_value=datetime(2026, 11, 28, 12, 0)
		), patch.object(mrs.frappe.db, "commit"):
			mrs.sync_project_merge_requests(PROJECT)
			mrs.sync_project_merge_requests(PROJECT)
		self.assertTrue(calls[0]["updated_after"].startswith("2024-11-28"))
		self.assertEqual((calls[0]["order_by"], calls[0]["sort"]), ("updated_at", "asc"))
		# the second run starts at the last merge request's update time, not at "now"
		self.assertEqual(calls[1]["updated_after"], "2026-11-20T10:00:00Z")

	def test_a_failing_merge_request_stops_the_project_there(self):
		def upsert(project, mr, patterns=None):
			if mr["iid"] == 2:
				raise frappe.ValidationError("broken")
			return "ok"

		batch = [_mr(iid=1, updated="2026-11-01T10:00:00.000Z"), _mr(iid=2, updated="2026-11-02T10:00:00.000Z"), _mr(iid=3, updated="2026-11-03T10:00:00.000Z")]
		with patch.object(mrs, "_get_all", return_value=batch), patch.object(mrs, "upsert_merge_request", side_effect=upsert), patch.object(
			mrs.frappe.db, "commit"
		), patch.object(mrs.frappe.db, "rollback"):
			self.assertEqual(mrs.sync_project_merge_requests(PROJECT), 1)
		# synced up to the first one only: the failing one comes again next time
		synced = frappe.db.get_value("GitLab Project", PROJECT, "merge_requests_synced_at")
		self.assertEqual(mrs._iso_utc(synced), "2026-11-01T10:00:00Z")

	def test_empty_diffs_are_counted_again_later(self):
		with patch.object(mrs, "_diffs", return_value=[]) as diffs:
			name = mrs.upsert_merge_request(PROJECT, _mr(iid=20, sha="h"))
			self.assertFalse(frappe.db.get_value("GitLab Merge Request", name, "sha"))
			diffs.return_value = [_diff("a.py", 3, 0)]
			mrs.upsert_merge_request(PROJECT, _mr(iid=20, sha="h"))
		self.assertEqual(frappe.db.get_value("GitLab Merge Request", name, ["sha", "lines_added"]), ("h", 3))

	def test_falls_back_to_changes_without_the_diffs_endpoint(self):
		import requests as real_requests

		class NotFound:
			status_code = 404

		class Changes:
			def raise_for_status(self):
				pass

			def json(self):
				return {"changes": [_diff("a.py", 1, 1)]}

		error = real_requests.HTTPError(response=NotFound())
		with patch.object(mrs, "_get_all", side_effect=error), patch.object(mrs.requests, "get", return_value=Changes()), patch.object(
			mrs, "_api", return_value="https://git.example.com/api"
		):
			self.assertEqual(len(mrs._diffs(PROJECT, 1)), 1)

	def test_webhook_queues_the_update(self):
		with patch.object(mrs.frappe, "enqueue") as enqueue:
			mrs.handle_merge_request_webhook({"project": {"id": PROJECT}, "object_attributes": {"iid": 12}})
		self.assertEqual(enqueue.call_args.kwargs["iid"], 12)

	def test_the_queued_update_fetches_the_merge_request(self):
		class Response:
			def raise_for_status(self):
				pass

			def json(self):
				return _mr(iid=12)

		with patch.object(mrs.requests, "get", return_value=Response()), patch.object(mrs, "_diffs", return_value=[]), patch.object(
			mrs, "_api", return_value="https://git.example.com/api"
		):
			mrs.update_merge_request(PROJECT, 12)
		self.assertTrue(frappe.db.exists("GitLab Merge Request", {"gitlab_project": PROJECT, "iid": 12}))

	def test_webhook_of_an_unknown_project_is_ignored(self):
		with patch.object(mrs.frappe, "enqueue") as enqueue:
			mrs.handle_merge_request_webhook({"project": {"id": "nope"}, "object_attributes": {"iid": 1}})
		enqueue.assert_not_called()
