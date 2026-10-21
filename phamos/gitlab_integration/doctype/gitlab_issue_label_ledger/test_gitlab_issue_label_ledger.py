# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import label_ledger
from phamos.gitlab_integration.label_ledger import _build_label_intervals


def _event(event_id, action, label, created_at, user="dev"):
	return {
		"id": event_id,
		"action": action,
		"label": {"name": label} if label else None,
		"created_at": created_at,
		"user": {"username": user},
	}


class TestBuildLabelIntervals(FrappeTestCase):
	def test_add_then_remove(self):
		intervals = _build_label_intervals(
			[
				_event(1, "add", "bug", "2026-01-01T10:00:00Z", "alice"),
				_event(2, "remove", "bug", "2026-01-05T10:00:00Z", "bob"),
			]
		)
		self.assertEqual(len(intervals), 1)
		self.assertEqual(intervals[0]["gitlab_event_id"], "1")
		self.assertEqual(intervals[0]["added_by"], "alice")
		self.assertEqual(intervals[0]["removed_at"], datetime(2026, 1, 5, 10))
		self.assertEqual(intervals[0]["removed_by"], "bob")

	def test_re_add_while_open_is_ignored(self):
		intervals = _build_label_intervals(
			[
				_event(1, "add", "bug", "2026-01-01T10:00:00Z"),
				_event(2, "add", "bug", "2026-01-02T10:00:00Z"),
			]
		)
		self.assertEqual([i["gitlab_event_id"] for i in intervals], ["1"])
		self.assertIsNone(intervals[0]["removed_at"])

	def test_re_add_after_remove_opens_new_interval(self):
		intervals = _build_label_intervals(
			[
				_event(1, "add", "bug", "2026-01-01T10:00:00Z"),
				_event(2, "remove", "bug", "2026-01-02T10:00:00Z"),
				_event(3, "add", "bug", "2026-01-03T10:00:00Z"),
			]
		)
		self.assertEqual([i["gitlab_event_id"] for i in intervals], ["1", "3"])
		self.assertIsNotNone(intervals[0]["removed_at"])
		self.assertIsNone(intervals[1]["removed_at"])

	def test_remove_without_add_is_ignored(self):
		self.assertEqual(_build_label_intervals([_event(1, "remove", "bug", "2026-01-01T10:00:00Z")]), [])

	def test_events_are_sorted_before_pairing(self):
		intervals = _build_label_intervals(
			[
				_event(2, "remove", "bug", "2026-01-05T10:00:00Z"),
				_event(1, "add", "bug", "2026-01-01T10:00:00Z"),
			]
		)
		self.assertEqual(len(intervals), 1)
		self.assertEqual(intervals[0]["removed_at"], datetime(2026, 1, 5, 10))

	def test_same_timestamp_falls_back_to_event_id(self):
		intervals = _build_label_intervals(
			[
				_event(2, "remove", "bug", "2026-01-01T10:00:00Z"),
				_event(1, "add", "bug", "2026-01-01T10:00:00Z"),
			]
		)
		self.assertEqual(len(intervals), 1)
		self.assertIsNotNone(intervals[0]["removed_at"])

	def test_events_for_deleted_labels_are_skipped(self):
		self.assertEqual(_build_label_intervals([_event(1, "add", None, "2026-01-01T10:00:00Z")]), [])


class TestSyncIssueLabelLedger(FrappeTestCase):
	"""sync_issue_label_ledger against existing rows, with GitLab mocked out."""

	def setUp(self):
		project = frappe.get_doc({"doctype": "GitLab Project", "project_id": "test-ledger-project"})
		project.insert(ignore_permissions=True, ignore_if_duplicate=True)
		self.ISSUE = (
			frappe.get_doc({"doctype": "GitLab Issue", "issue_id": 1, "gitlab_project": project.name})
			.insert(ignore_permissions=True)
			.name
		)

	def tearDown(self):
		frappe.db.rollback()

	def _insert_row(self, event_id, label, added_at, removed_at=None):
		frappe.get_doc(
			{
				"doctype": label_ledger.LEDGER_DOCTYPE,
				"gitlab_issue": self.ISSUE,
				"gitlab_event_id": event_id,
				"label": label,
				"added_at": added_at,
				"removed_at": removed_at,
			}
		).insert(ignore_permissions=True)

	def _rows(self):
		return {
			row.gitlab_event_id: row
			for row in frappe.get_all(
				label_ledger.LEDGER_DOCTYPE,
				filters={"gitlab_issue": self.ISSUE},
				fields=["gitlab_event_id", "label", "removed_at"],
			)
		}

	def _sync(self, events=None, error=None):
		with patch.object(
			label_ledger, "get_label_events_for_project_issue", return_value=events, side_effect=error
		):
			label_ledger.sync_issue_label_ledger(self.ISSUE)

	def test_closed_row_is_not_reopened_by_missing_remove_event(self):
		self._insert_row("1", "bug", datetime(2026, 1, 1, 10), datetime(2026, 1, 5, 10))
		self._sync([_event(1, "add", "bug", "2026-01-01T10:00:00Z")])
		self.assertEqual(self._rows()["1"].removed_at, datetime(2026, 1, 5, 10))

	def test_open_row_of_deleted_label_is_closed(self):
		self._insert_row("1", "old-label", datetime(2026, 1, 1, 10))
		self._sync(
			[
				_event(1, "add", None, "2026-01-01T10:00:00Z"),
				_event(2, "remove", None, "2026-01-03T10:00:00Z"),
			]
		)
		self.assertEqual(self._rows()["1"].removed_at, datetime(2026, 1, 3, 10))

	def test_failed_fetch_leaves_ledger_untouched(self):
		self._insert_row("1", "bug", datetime(2026, 1, 1, 10))
		self.assertRaises(frappe.ValidationError, self._sync, error=frappe.ValidationError)
		self.assertIsNone(self._rows()["1"].removed_at)

	def test_renamed_label_updates_open_and_closed_rows(self):
		self._insert_row("1", "bug", datetime(2026, 1, 1, 10), datetime(2026, 1, 2, 10))
		self._insert_row("3", "bug", datetime(2026, 1, 3, 10))
		self._sync(
			[
				_event(1, "add", "type::bug", "2026-01-01T10:00:00Z"),
				_event(2, "remove", "type::bug", "2026-01-02T10:00:00Z"),
				_event(3, "add", "type::bug", "2026-01-03T10:00:00Z"),
			]
		)
		rows = self._rows()
		self.assertEqual((rows["1"].label, rows["3"].label), ("type::bug", "type::bug"))
		self.assertFalse(label_ledger.label_ledger_needs_sync(self.ISSUE, ["type::bug"]))
