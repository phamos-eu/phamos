# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


# Privacy mode of the HR Cockpit (#1839): shorter than this and the data is gone before it can be read.
MIN_PRIVACY_REVEAL_SECONDS = 10


class phamosSettings(Document):
	def validate(self):
		seconds = self.human_resources_privacy_reveal_seconds
		if seconds is not None and seconds < MIN_PRIVACY_REVEAL_SECONDS:
			frappe.throw(
				frappe._("Privacy mode must show data for at least {0} seconds.").format(MIN_PRIVACY_REVEAL_SECONDS)
			)

	def before_save(self):
		self._sync_mattermost_scheduler()
		self._sync_raven_scheduler()

	def _sync_mattermost_scheduler(self):
		job_name = "mattermost_daily_thread.create_mattermost_thread"
		if not frappe.db.exists("Scheduled Job Type", job_name):
			return

		cron_doc = frappe.get_doc("Scheduled Job Type", job_name)
		cron_doc.stopped = 0 if self.enable_daily_thread_creation else 1

		if self.thread_posting_hour:
			cron_doc.cron_format = f"0 {self.thread_posting_hour} * * 1-5"

		cron_doc.save(ignore_permissions=True)

	def _sync_raven_scheduler(self):
		job_name = "raven_daily_thread.create_raven_thread"
		if not frappe.db.exists("Scheduled Job Type", job_name):
			return

		cron_doc = frappe.get_doc("Scheduled Job Type", job_name)
		cron_doc.stopped = 0 if self.enable_raven_daily_thread else 1

		hour = self.thread_posting_hour_raven or 6
		cron_doc.cron_format = f"0 {hour} * * 1-5"
		cron_doc.save(ignore_permissions=True)
