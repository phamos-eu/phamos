# Copyright (c) 2025, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestGitLabIssue(FrappeTestCase):
	def test_issue_link_is_editable(self):
		"""The link to the ERPNext Issue shows on every record and can be set by hand (#1936)."""
		field = frappe.get_meta("GitLab Issue").get_field("issue")
		self.assertEqual(field.fieldtype, "Link")
		self.assertEqual(field.options, "Issue")
		self.assertFalse(field.read_only)
		self.assertFalse(field.hidden)
