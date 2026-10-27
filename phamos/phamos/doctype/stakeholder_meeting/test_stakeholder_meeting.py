# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.phamos.doctype.implementation_chapter.implementation_chapter import (
	get_chapter_history,
	set_as_planned,
)


def make_implementation():
	customer = frappe.db.get_value("Customer", {"customer_name": "_Test Stakeholder Customer"})
	if not customer:
		customer = (
			frappe.get_doc({"doctype": "Customer", "customer_name": "_Test Stakeholder Customer"})
			.insert(ignore_permissions=True)
			.name
		)

	implementation = frappe.get_doc({"doctype": "Implementation", "customer": customer})
	implementation.insert(set_name=f"_Test Impl {frappe.generate_hash(length=6)}", ignore_permissions=True)
	return implementation


def make_chapter(implementation, title="Chapter A", plan=True):
	chapter = frappe.get_doc(
		{
			"doctype": "Implementation Chapter",
			"implementation": implementation,
			"status": "Draft",
			"chapter_title": title,
			"full_chapter_description": f"{title} description",
			"planned_start": "2026-01-01",
			"target_date": "2026-06-30",
			"current_level": 1,
			"target_level": 3,
		}
	).insert(ignore_permissions=True)
	if plan:
		set_as_planned(chapter.name)
		chapter.reload()
	return chapter


def make_meeting(implementation, meeting_date="2026-02-01"):
	if not frappe.db.exists("Meeting Type", "_Test Review"):
		frappe.get_doc({"doctype": "Meeting Type", "meeting_type_name": "_Test Review"}).insert()

	return frappe.get_doc(
		{
			"doctype": "Stakeholder Meeting",
			"implementation": implementation,
			"meeting_type": "_Test Review",
			"meeting_date": meeting_date,
			"chair": "Administrator",
		}
	).insert()


def set_progress(meeting, **values):
	for row in meeting.chapter_reviews:
		row.progress = "On Track"
		row.update(values)


class TestStakeholderMeeting(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()
		self.chapter = make_chapter(self.implementation.name)

	def test_seeds_planned_chapters(self):
		make_chapter(self.implementation.name, title="Draft Chapter", plan=False)
		meeting = make_meeting(self.implementation.name)

		self.assertEqual([row.chapter for row in meeting.chapter_reviews], [self.chapter.name])
		row = meeting.chapter_reviews[0]
		self.assertEqual(row.current_revision, self.chapter.current_revision)
		self.assertEqual((row.current_level_before, row.target_level_before), (1, 3))

	def test_submit_with_level_change_creates_revision(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, current_level=2)
		meeting.submit()

		self.chapter.reload()
		row = meeting.chapter_reviews[0]
		row.reload()
		self.assertEqual(self.chapter.current_level, 2)
		self.assertEqual(self.chapter.last_meeting, meeting.name)
		self.assertNotEqual(self.chapter.current_revision, row.previous_revision)
		self.assertEqual(self.chapter.current_revision, row.current_revision)
		self.assertEqual(
			frappe.db.get_value("Implementation Chapter Revision", row.current_revision, "revision_number"), 2
		)

	def test_submit_keeps_newer_live_level_when_unchanged_in_meeting(self):
		meeting = make_meeting(self.implementation.name)

		self.chapter.reload()
		self.chapter.current_level = 2
		self.chapter.save()

		meeting.reload()
		set_progress(meeting)
		meeting.submit()

		self.assertEqual(frappe.db.get_value("Implementation Chapter", self.chapter.name, "current_level"), 2)

	def test_scope_change_updates_locked_content(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(
			meeting,
			scope_change=1,
			proposed_chapter_title="Chapter A v2",
			proposed_full_chapter_description="New scope",
			proposed_planned_start="2026-02-01",
			proposed_target_date="2026-09-30",
		)
		meeting.submit()

		self.chapter.reload()
		self.assertEqual(self.chapter.chapter_title, "Chapter A v2")
		self.assertEqual(
			frappe.db.get_value("Implementation Chapter Revision", self.chapter.current_revision, "chapter_title"),
			"Chapter A v2",
		)

	def test_cancel_restores_chapter_and_implementation(self):
		self.implementation.reload()
		self.implementation.review_cadence = "Monthly"
		self.implementation.next_review_due = "2026-01-15"
		self.implementation.save()
		revision_before = self.chapter.current_revision

		meeting = make_meeting(self.implementation.name)
		set_progress(
			meeting,
			current_level=2,
			chapter_status_after="In Progress",
			scope_change=1,
			proposed_chapter_title="Chapter A v2",
			proposed_full_chapter_description="New scope",
			proposed_planned_start="2026-02-01",
			proposed_target_date="2026-09-30",
		)
		meeting.submit()
		meeting.reload()
		created_revision = meeting.chapter_reviews[0].current_revision

		meeting.cancel()

		self.chapter.reload()
		self.assertEqual(self.chapter.current_revision, revision_before)
		self.assertEqual(self.chapter.status, "Planned")
		self.assertEqual(self.chapter.current_level, 1)
		self.assertEqual(self.chapter.chapter_title, "Chapter A")
		self.assertFalse(self.chapter.last_meeting)
		self.assertFalse(frappe.db.exists("Implementation Chapter Revision", created_revision))

		self.implementation.reload()
		self.assertFalse(self.implementation.last_stakeholder_meeting)
		self.assertEqual(str(self.implementation.next_review_due), "2026-01-15")

	def test_cancel_blocked_while_later_meeting_is_submitted(self):
		first = make_meeting(self.implementation.name)
		set_progress(first)
		first.submit()

		second = make_meeting(self.implementation.name, meeting_date="2026-03-01")
		set_progress(second)
		second.submit()

		first.reload()
		self.assertRaises(frappe.ValidationError, first.cancel)

		second.cancel()
		first.reload()
		first.cancel()
		self.assertEqual(first.docstatus, 2)

	def test_rejects_chapter_from_another_implementation(self):
		other_chapter = make_chapter(make_implementation().name)
		meeting = make_meeting(self.implementation.name)
		meeting.append("chapter_reviews", {"chapter": other_chapter.name})
		self.assertRaises(frappe.ValidationError, meeting.save)

	def test_history_maps_each_revision_to_the_meeting_that_created_it(self):
		first = make_meeting(self.implementation.name)
		set_progress(first, current_level=2, decision="Yes")
		first.submit()

		second = make_meeting(self.implementation.name, meeting_date="2026-03-01")
		set_progress(second, progress="At Risk")
		second.submit()

		revisions = {rev.revision_number: rev for rev in get_chapter_history(self.chapter.name)["revisions"]}
		self.assertIsNone(revisions[1].progress)
		self.assertEqual(revisions[2].progress, "On Track")
		self.assertEqual(revisions[2].decision, "Yes")
		self.assertTrue(revisions[2].is_current)

	def test_submit_rejects_meeting_dated_before_last_meeting(self):
		later = make_meeting(self.implementation.name, meeting_date="2026-03-01")
		set_progress(later)
		later.submit()

		earlier = make_meeting(self.implementation.name, meeting_date="2026-02-01")
		set_progress(earlier)
		self.assertRaises(frappe.ValidationError, earlier.submit)

	def test_cleared_level_keeps_chapter_level(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, current_level=None)
		meeting.submit()

		self.chapter.reload()
		self.assertEqual(self.chapter.current_level, 1)
		self.assertEqual(self.chapter.current_revision, meeting.chapter_reviews[0].current_revision)

	def test_cancel_blocked_when_chapter_edited_after_submit(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, current_level=2)
		meeting.submit()

		self.chapter.reload()
		self.chapter.status = "Blocked"
		self.chapter.save()

		meeting.reload()
		self.assertRaises(frappe.ValidationError, meeting.cancel)

		self.chapter.reload()
		self.chapter.status = "Planned"
		self.chapter.save()
		meeting.reload()
		meeting.cancel()
		self.assertEqual(frappe.db.get_value("Implementation Chapter", self.chapter.name, "current_level"), 1)
