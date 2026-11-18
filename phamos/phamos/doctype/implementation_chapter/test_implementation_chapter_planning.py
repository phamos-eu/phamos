# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Chapter planning links and the WIP limits agreed with the customer (#1970)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_chapter.implementation_chapter import get_wip_status
from phamos.phamos.doctype.implementation_feature.test_implementation_feature import make_feature
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import make_chapter, make_implementation


class TestImplementationChapterPlanning(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()

	def test_dependencies_stay_in_the_implementation_and_have_no_loops(self):
		first = make_chapter(self.implementation.name, title="Setup")
		second = make_chapter(self.implementation.name, title="Go Live")
		second.append("depends_on", {"chapter": first.name})
		second.save()
		first.reload()
		first.append("depends_on", {"chapter": second.name})
		self.assertRaises(frappe.ValidationError, first.save)

		elsewhere = make_chapter(make_implementation().name, title="Elsewhere")
		second.reload()
		second.append("depends_on", {"chapter": elsewhere.name})
		self.assertRaises(frappe.ValidationError, second.save)

	def test_features_of_the_same_implementation_only(self):
		chapter = make_chapter(self.implementation.name, title="Warehouse")
		chapter.append("features", {"feature": make_feature(self.implementation.name).name})
		chapter.save()
		chapter.append("features", {"feature": make_feature(make_implementation().name).name})
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_over_the_agreed_limit_warns_but_does_not_block(self):
		frappe.db.set_value("Implementation", self.implementation.name, "max_parallel_chapters", 1)
		for title in ("Stock", "Selling"):
			chapter = make_chapter(self.implementation.name, title=title)
			frappe.message_log = []
			chapter.status = "In Progress"
			chapter.save()
		self.assertEqual(chapter.status, "In Progress")
		self.assertTrue(any("agreed with the customer" in str(message) for message in frappe.message_log))
		status = get_wip_status(self.implementation.name)
		self.assertEqual((status["chapters"], status["max_chapters"]), (2, 1))

	def test_feature_limit_warns_too(self):
		frappe.db.set_value("Implementation", self.implementation.name, "max_parallel_features", 1)
		make_feature(self.implementation.name, title="One", status="In Progress")
		frappe.message_log = []
		second = make_feature(self.implementation.name, title="Two", status="In Progress")
		self.assertEqual(second.status, "In Progress")
		self.assertTrue(any("agreed with the customer" in str(message) for message in frappe.message_log))

	def test_a_chapter_or_feature_is_listed_once(self):
		first = make_chapter(self.implementation.name, title="Setup")
		second = make_chapter(self.implementation.name, title="Go Live")
		second.append("depends_on", {"chapter": first.name})
		second.append("depends_on", {"chapter": first.name})
		self.assertRaises(frappe.ValidationError, second.save)
		second.reload()
		feature = make_feature(self.implementation.name)
		second.append("features", {"feature": feature.name})
		second.append("features", {"feature": feature.name})
		self.assertRaises(frappe.ValidationError, second.save)

	def test_limits_cannot_be_negative(self):
		implementation = frappe.get_doc("Implementation", self.implementation.name)
		implementation.max_parallel_chapters = -1
		self.assertRaises(frappe.ValidationError, implementation.save)
