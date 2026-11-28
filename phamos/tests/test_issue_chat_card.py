# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""#2234: the Issue chat's card lists status, priority, type, customer, Implementation, project, sender."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.setup import issue_chat_card


class TestIssueChatCard(FrappeTestCase):
	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_cache(doctype="Issue")

	def test_fields_are_in_preview_and_setup_runs_twice(self):
		frappe.db.delete("Property Setter", {"doc_type": "Issue", "property": "in_preview"})
		frappe.clear_cache(doctype="Issue")
		issue_chat_card.after_migrate()
		issue_chat_card.after_migrate()
		meta = frappe.get_meta("Issue")
		present = [f for f in issue_chat_card.PREVIEW_FIELDS if meta.has_field(f)]
		self.assertEqual([f for f in present if not meta.get_field(f).in_preview], [])
		self.assertEqual(frappe.db.count("Property Setter", {"doc_type": "Issue", "property": "in_preview"}), len(present))

	def test_raven_preview_returns_them(self):
		if "raven" not in frappe.get_installed_apps():
			self.skipTest("Raven is not installed")
		issue_chat_card.after_migrate()
		issue = frappe.get_doc({"doctype": "Issue", "subject": "Card test", "priority": frappe.db.get_value(
			"Issue Priority", {}, "name")}).insert(ignore_permissions=True)
		from raven.api.document_link import get_preview_data

		data = get_preview_data("Issue", issue.name)
		labels = {frappe.get_meta("Issue").get_label(f) for f in ("status", "priority")}
		self.assertTrue(labels & set(data), data)
