# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Patch backfill_chapter_revision_status_and_levels (#1071)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0.backfill_chapter_revision_status_and_levels import execute
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
	make_meeting,
	set_progress,
)

REVISION = "Implementation Chapter Revision"
FIELDS = ["status", "current_level", "target_level"]


def _as_before_migration(revision):
	"""What migrate leaves on a revision created before the fields existed."""
	frappe.db.set_value(
		REVISION,
		revision,
		{"status": "Draft", "current_level": None, "target_level": None},
		update_modified=False,
	)


class TestBackfillChapterRevisionStatus(FrappeTestCase):
	def setUp(self):
		implementation = make_implementation()
		self.chapter = make_chapter(implementation.name)
		self.older_revision = self.chapter.current_revision

		meeting = make_meeting(implementation.name)
		set_progress(meeting, current_level=2)
		meeting.submit()

		self.chapter.reload()
		self.chapter.status = "Blocked"
		self.chapter.save()
		self.current_revision = self.chapter.current_revision
		self.assertNotEqual(self.current_revision, self.older_revision)

		_as_before_migration(self.older_revision)
		_as_before_migration(self.current_revision)

	def test_current_revision_copies_the_chapter_status_and_levels(self):
		execute()

		current = frappe.db.get_value(REVISION, self.current_revision, FIELDS, as_dict=True)
		self.assertEqual((current.status, current.current_level, current.target_level), ("Blocked", 2, 3))

	def test_older_revisions_become_planned_with_unknown_levels(self):
		execute()

		older = frappe.db.get_value(REVISION, self.older_revision, FIELDS, as_dict=True)
		self.assertEqual(older.status, "Planned")
		self.assertFalse(older.current_level)
		self.assertFalse(older.target_level)

	def test_running_twice_changes_nothing(self):
		execute()
		first_run = frappe.db.get_value(REVISION, self.current_revision, FIELDS, as_dict=True)
		execute()
		self.assertEqual(frappe.db.get_value(REVISION, self.current_revision, FIELDS, as_dict=True), first_run)
