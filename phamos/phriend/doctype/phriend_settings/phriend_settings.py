import frappe
from frappe.model.document import Document

from phamos.phriend.shortcut import normalize


class PhriendSettings(Document):
	def validate(self):
		if self.gitlab_url:
			self.gitlab_url = self.gitlab_url.strip().rstrip("/")
		if self.gitlab_project:
			self.gitlab_project = self.gitlab_project.strip().strip("/")
		# one spelling ("cmd+p" -> "Mod+P"); empty means no shortcut for anyone who kept the default
		self.shortcut = normalize(self.shortcut)

	def on_update(self):
		# Desk caches each user's boot (frappe.boot.phriend: on/off, shortcut) until the next
		# login; drop it so a changed setting reaches Desk on the next reload, as in the cockpits
		frappe.cache.delete_key("bootinfo")
