# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_implementation


def make_entry(doctype_name="Delivery Trip", app="phamos_logistics", **values):
	return frappe.get_doc(
		{"doctype": "Implementation Doctype", "doctype_name": doctype_name, "app": app, **values}
	).insert(ignore_permissions=True)


class TestImplementationDoctype(FrappeTestCase):
	def test_named_by_doctype_and_app(self):
		self.assertEqual(make_entry().name, "Delivery Trip · phamos_logistics")
		self.assertEqual(make_entry("Pick List Print", app="").name, "Pick List Print")

	def test_whoever_sets_showcase_is_the_reviewer(self):
		entry = make_entry("Route Planner Review", showcase=1, showcase_reviewed_by="Guest")
		self.assertEqual(entry.showcase_reviewed_by, frappe.session.user)

	def test_reviewer_cannot_be_overwritten_later(self):
		entry = make_entry("Route Planner Keep", showcase=1)
		entry.showcase_reviewed_by = "Guest"  # as an API write would
		entry.save()
		self.assertEqual(entry.showcase_reviewed_by, frappe.session.user)

	def test_changed_content_withdraws_the_showcase(self):
		entry = make_entry("Route Planner Content", showcase=1, description="Plans tours")
		entry.description = "Plans tours for Customer X with their prices"
		entry.save()
		self.assertFalse(entry.showcase)
		self.assertIsNone(entry.showcase_reviewed_by)

	def test_used_in_lists_the_implementations_of_its_features(self):
		entry = make_entry("Batch Label", app="phamos")
		self.assertEqual(entry.used_in_implementations, "")
		implementation = make_implementation()
		make_feature(
			implementation.name,
			doctypes=[{"implementation_doctype": entry.name, "work_done": "Print format with batch and best-before"}],
		)
		self.assertEqual(entry.used_in_implementations, implementation.name)
