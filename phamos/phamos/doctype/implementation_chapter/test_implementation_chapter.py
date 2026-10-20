# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_chapter.implementation_chapter import (
	get_chapter_history,
)
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
)


class TestImplementationChapter(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()

	def test_draft_can_be_cancelled(self):
		chapter = make_chapter(self.implementation.name, plan=False)
		chapter.status = "Cancelled"
		chapter.save()
		self.assertEqual(chapter.status, "Cancelled")

	def test_draft_cannot_skip_to_in_progress(self):
		chapter = make_chapter(self.implementation.name, plan=False)
		chapter.status = "In Progress"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_draft_cannot_be_planned_without_set_as_planned(self):
		chapter = make_chapter(self.implementation.name, plan=False)
		chapter.status = "Planned"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_planned_cannot_go_back_to_draft(self):
		chapter = make_chapter(self.implementation.name)
		chapter.status = "Draft"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_agreed_content_locked_after_planning(self):
		chapter = make_chapter(self.implementation.name)
		chapter.chapter_title = "Renamed"
		self.assertRaises(frappe.ValidationError, chapter.save)

	def test_status_change_syncs_to_current_revision(self):
		chapter = make_chapter(self.implementation.name)
		chapter.status = "Blocked"
		chapter.save()
		self.assertEqual(
			frappe.db.get_value("Implementation Chapter Revision", chapter.current_revision, "status"), "Blocked"
		)

	def test_revision_is_immutable(self):
		chapter = make_chapter(self.implementation.name)
		revision = frappe.get_doc("Implementation Chapter Revision", chapter.current_revision)

		revision.chapter_title = "Edited"
		self.assertRaises(frappe.ValidationError, revision.save)
		self.assertRaises(frappe.ValidationError, revision.delete)

	def test_history_requires_read_permission(self):
		chapter = make_chapter(self.implementation.name)
		frappe.set_user("Guest")
		try:
			self.assertRaises(frappe.PermissionError, get_chapter_history, chapter.name)
		finally:
			frappe.set_user("Administrator")
