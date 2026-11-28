# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Timesheet Record submit no longer waits on, or rolls back for, the GitLab Issue (#1636).

The touch-time and cycle-time hooks only queue a job that runs after the submit is committed, and
the retry helper retries a lock timeout without undoing the rest of the transaction.
"""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.gitlab_integration import gitlab_utils


class TestGitLabIssueTimesheetSync(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		self.issue = self._issue("Lock contention")

	def tearDown(self):
		frappe.db.rollback()

	def _issue(self, title):
		return frappe.get_doc({"doctype": "GitLab Issue", "title": title}).insert(ignore_permissions=True).name

	def _record(self):
		return frappe._dict(doctype="Timesheet Record", name="TR-TEST", gitlab_issue=self.issue)

	def test_submit_hooks_queue_jobs_after_commit_instead_of_writing_the_issue(self):
		with (
			patch.object(gitlab_utils, "_set_gitlab_issue_value_with_retry") as write,
			patch("frappe.enqueue") as enqueue,
		):
			gitlab_utils.sync_touch_time_on_timesheet_change(self._record())
			gitlab_utils.sync_cycle_time_start_on_timesheet_change(self._record())

		write.assert_not_called()
		self.assertEqual(
			[(c.args[0], c.kwargs) for c in enqueue.call_args_list],
			[
				(
					"phamos.gitlab_integration.gitlab_utils.sync_touch_time",
					{"issue_name": self.issue, "enqueue_after_commit": True},
				),
				(
					"phamos.gitlab_integration.gitlab_utils.sync_cycle_time_start",
					{"issue_name": self.issue, "enqueue_after_commit": True},
				),
			],
		)

	def test_jobs_reach_the_queue_only_on_commit(self):
		# Run the after-commit callbacks by hand: tests never really commit.
		with patch("frappe.utils.background_jobs.get_queue") as get_queue:
			queued = get_queue.return_value.enqueue_call
			frappe.db.after_commit.reset()

			gitlab_utils.sync_touch_time_on_timesheet_change(self._record())
			queued.assert_not_called()
			frappe.db.rollback()
			frappe.db.after_commit.run()
			queued.assert_not_called()

			gitlab_utils.sync_touch_time_on_timesheet_change(self._record())
			frappe.db.after_commit.run()
			queued.assert_called_once()

	def test_record_without_issue_queues_nothing(self):
		with patch("frappe.enqueue") as enqueue:
			gitlab_utils.sync_touch_time_on_timesheet_change(frappe._dict(gitlab_issue=None))
			gitlab_utils.sync_cycle_time_start_on_timesheet_change(frappe._dict(gitlab_issue=None))
		enqueue.assert_not_called()

	def test_touch_time_job_recalculates_the_issue(self):
		frappe.db.set_value("GitLab Issue", self.issue, "total_touch_time", 999)
		gitlab_utils.sync_touch_time(self.issue)
		self.assertEqual(frappe.db.get_value("GitLab Issue", self.issue, "total_touch_time"), 0)

	def test_retry_after_a_lock_timeout_keeps_earlier_writes(self):
		other = self._issue("Written earlier in the same request")
		frappe.db.set_value("GitLab Issue", other, "state", "closed")
		real_set_value = frappe.db.set_value
		calls = []

		def set_value_locked_once(*args, **kwargs):
			calls.append(args)
			if len(calls) == 1:
				raise frappe.QueryTimeoutError("Lock wait timeout exceeded")
			return real_set_value(*args, **kwargs)

		with patch.object(frappe.db, "set_value", side_effect=set_value_locked_once), patch.object(
			gitlab_utils.time, "sleep"
		):
			gitlab_utils._set_gitlab_issue_value_with_retry(self.issue, {"total_touch_time": 60})

		self.assertEqual(len(calls), 2)
		self.assertEqual(frappe.db.get_value("GitLab Issue", other, "state"), "closed")
		self.assertEqual(frappe.db.get_value("GitLab Issue", self.issue, "total_touch_time"), 60)
