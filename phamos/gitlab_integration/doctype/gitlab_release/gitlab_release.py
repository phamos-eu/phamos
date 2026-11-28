# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""GitLab Release (#1985): a release of a GitLab project, synced read-only from GitLab.

Planning happens in Implementation Release (#1986), which links to the GitLab Release once
the tag exists. Nothing here is written back to GitLab.
"""

from frappe.model.document import Document


class GitLabRelease(Document):
	def autoname(self):
		# a tag is unique per project, not across projects
		self.name = f"{self.gitlab_project}-{self.tag_name}"
