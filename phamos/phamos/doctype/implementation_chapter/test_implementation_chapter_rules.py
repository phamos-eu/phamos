# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Implementation Chapter rules not covered by test_implementation_chapter (#1071)."""

from datetime import date

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import getdate

from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
)

REVISION = "Implementation Chapter Revision"


class TestImplementationChapterRules(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()

	def test_draft_cannot_skip_to_blocked(self):
		chapter = make_chapter(self.implementation.name, plan=False)
		chapter.status = "Blocked"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_cancelled_is_final(self):
		chapter = make_chapter(self.implementation.name, plan=False)
		chapter.status = "Cancelled"
		chapter.save()

		chapter.status = "In Progress"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_unchanged_date_given_as_a_string_is_not_a_content_change(self):
		chapter = make_chapter(self.implementation.name)
		chapter.planned_start = "2026-01-01"
		chapter.target_date = "2026-06-30"
		chapter.save()

		self.assertEqual(getdate(chapter.planned_start), date(2026, 1, 1))

	def test_set_as_planned_freezes_revision_one(self):
		chapter = make_chapter(self.implementation.name)
		revision = frappe.get_doc(REVISION, chapter.current_revision)

		self.assertEqual(chapter.status, "Planned")
		self.assertEqual(revision.revision_number, 1)
		self.assertEqual(revision.status, "Planned")
		self.assertEqual((revision.current_level, revision.target_level), (1, 3))
		self.assertEqual(revision.chapter_title, "Chapter A")

	def test_direct_level_edit_updates_the_current_revision_in_place(self):
		chapter = make_chapter(self.implementation.name)
		chapter.current_level = 2
		chapter.save()

		self.assertEqual(frappe.db.count(REVISION, {"implementation_chapter": chapter.name}), 1)
		self.assertEqual(frappe.db.get_value(REVISION, chapter.current_revision, "current_level"), 2)
