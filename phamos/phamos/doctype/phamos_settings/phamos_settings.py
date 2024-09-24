# Copyright (c) 2023, phamos.eu and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe

class phamosSettings(Document):
	def before_save(self):
		if self.enable_daily_thread_creation == 0:
			cron_doc = frappe.get_doc("Scheduled Job Type","mattermost_daily_thread.create_mattermost_thread")
			cron_doc.stopped = 1
			cron_doc.save(ignore_permissions=True)
		elif self.enable_daily_thread_creation == 1:
			cron_doc = frappe.get_doc("Scheduled Job Type","mattermost_daily_thread.create_mattermost_thread")
			cron_doc.stopped = 0
			cron_doc.save(ignore_permissions=True)
		if self.thread_posting_hour:
			cron_format = f"0 {self.thread_posting_hour} * * 1-5"
			cron_doc = frappe.get_doc("Scheduled Job Type","mattermost_daily_thread.create_mattermost_thread")
			cron_doc.cron_format = cron_format
			cron_doc.save(ignore_permissions=True)
		

