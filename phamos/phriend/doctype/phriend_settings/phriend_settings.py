from urllib.parse import urlparse

import frappe
from frappe import _
from frappe.model.document import Document

from phamos.phriend.shortcut import normalize

# Plain http only to a system on this machine or the local network (a local test of the target).
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
LOCAL_SUFFIXES = (".localhost", ".local", ".test")


class PhriendSettings(Document):
	def validate(self):
		if self.gitlab_url:
			self.gitlab_url = self.gitlab_url.strip().rstrip("/")
		if self.gitlab_project:
			self.gitlab_project = self.gitlab_project.strip().strip("/")
		# one spelling ("cmd+p" -> "Mod+P"); empty means no shortcut for anyone who kept the default
		self.shortcut = normalize(self.shortcut)
		self.validate_target()

	def validate_target(self):
		"""The target system gets the reports with an API key: only over https, except locally."""
		self.target_url = (self.target_url or "").strip().rstrip("/")
		self.target_api_key = (self.target_api_key or "").strip()
		if not self.target_url:
			return
		url = urlparse(self.target_url)
		host = (url.hostname or "").lower()
		local = host in LOCAL_HOSTS or host.endswith(LOCAL_SUFFIXES)
		if not host or url.path not in ("", "/") or url.query or url.fragment:
			frappe.throw(_("Target URL: only the address of the system, like https://erp.example.com"))
		if url.scheme != "https" and not (url.scheme == "http" and local):
			frappe.throw(_("Target URL must start with https://"))

	def on_update(self):
		# Desk caches each user's boot (frappe.boot.phriend: on/off, shortcut, target) until the
		# next login; drop it so a changed setting reaches Desk on the next reload, as in the cockpits
		frappe.cache.delete_key("bootinfo")
