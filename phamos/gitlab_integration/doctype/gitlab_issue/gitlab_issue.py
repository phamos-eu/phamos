# Copyright (c) 2025, phamos.eu
# For license information, please see license.txt

from frappe.model.document import Document


class GitLabIssue(Document):
    def autoname(self):
        if not self.gitlab_project or not self.issue_id:
            return

        # Use the linked GitLab Project docname (project_id) to avoid collisions
        # when multiple projects share the same human title.
        self.name = f"{self.gitlab_project}-{self.issue_id}"
