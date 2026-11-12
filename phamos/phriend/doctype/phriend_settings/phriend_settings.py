from frappe.model.document import Document


class PhriendSettings(Document):
	def validate(self):
		if self.gitlab_url:
			self.gitlab_url = self.gitlab_url.strip().rstrip("/")
		if self.gitlab_project:
			self.gitlab_project = self.gitlab_project.strip().strip("/")
