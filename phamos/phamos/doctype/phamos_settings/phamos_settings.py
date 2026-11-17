# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class phamosSettings(Document):
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
