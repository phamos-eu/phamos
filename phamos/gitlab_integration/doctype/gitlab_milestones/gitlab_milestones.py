# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import now_datetime


class GitLabMilestones(Document):
	def validate(self):
		# GitLab gives no closing date for milestones, and the sync saves every milestone on every run
		# (so `modified` is always today). Remember when we saw it change to closed (Team successes, #1981).
		# A milestone first synced as closed gets no date: when it closed is unknown.
		if self.state == "closed":
			if not self.closed_on and not self.is_new() and self.has_value_changed("state"):
				self.closed_on = now_datetime()
		else:
			self.closed_on = None
