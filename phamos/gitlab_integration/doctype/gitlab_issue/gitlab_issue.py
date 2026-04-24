# Copyright (c) 2025, phamos.eu
# For license information, please see license.txt

import frappe
import re
from frappe.model.document import Document


class GitLabIssue(Document):
    def autoname(self):
        if not self.gitlab_project or not self.issue_id:
            return

        project_title = frappe.db.get_value(
            "GitLab Project",
            self.gitlab_project,
            "title"
        )

        if not project_title:
            return

        project_title = re.sub(r"\s+", "-", project_title.strip().lower())

        self.name = f"{project_title}-{self.issue_id}"
        # frappe.msgprint(f"GitLab Issue named as: {self.name}")
