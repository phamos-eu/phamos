# Copyright (c) 2026, phamos.eu and Contributors
# See license.txt

"""Stakeholder Meeting rules not covered by test_stakeholder_meeting (#1071)."""

import frappe
from frappe.tests.utils import FrappeTestCase

from phamos.patches.v1_0 import backfill_reviewed_revision_on_meeting_reviews
from phamos.phamos.doctype.implementation_chapter.implementation_chapter import (
	get_chapter_history,
	set_as_planned,
)
from phamos.phamos.doctype.stakeholder_meeting.stakeholder_meeting import get_chapter_review_row
from phamos.phamos.doctype.stakeholder_meeting.test_stakeholder_meeting import (
	make_chapter,
	make_implementation,
	make_meeting,
	set_progress,
)

REVISION = "Implementation Chapter Revision"
REVIEW_ROW = "Stakeholder Meeting Chapter Review"


class TestStakeholderMeetingSubmitRules(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()
		self.chapter = make_chapter(self.implementation.name)

	def test_submit_requires_progress_on_every_row(self):
		meeting = make_meeting(self.implementation.name)
		self.assertRaises(frappe.ValidationError, meeting.submit)

	def test_scope_change_requires_the_proposed_content(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, scope_change=1, proposed_chapter_title="Only a title")

		self.assertRaises(frappe.ValidationError, meeting.submit)
		self.assertEqual(
			frappe.db.get_value("Implementation Chapter", self.chapter.name, "chapter_title"), "Chapter A"
		)

	def test_a_chapter_is_reviewed_only_once_per_meeting(self):
		meeting = make_meeting(self.implementation.name)
		meeting.append("chapter_reviews", {"chapter": self.chapter.name})
		self.assertRaises(frappe.ValidationError, meeting.save)

	def test_decision_is_recorded_without_a_scope_change(self):
		revision_before = self.chapter.current_revision

		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, decision="Yes", decision_description="Chapter complete")
		meeting.submit()

		self.chapter.reload()
		self.assertEqual(self.chapter.decision, "Yes")
		self.assertEqual(self.chapter.decision_description, "Chapter complete")
		self.assertEqual(self.chapter.current_revision, revision_before)

		history = get_chapter_history(self.chapter.name)["revisions"]
		self.assertEqual(history[0]["decision"], "Yes")

		meeting.reload()
		meeting.cancel()
		self.chapter.reload()
		self.assertFalse(self.chapter.decision)
		self.assertFalse(self.chapter.decision_description)

	def test_complete_progress_is_recorded_in_history(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, progress="Complete")
		meeting.submit()

		revisions = get_chapter_history(self.chapter.name)["revisions"]
		self.assertEqual(revisions[0]["progress"], "Complete")

	def test_meeting_can_mark_a_chapter_completed(self):
		revision_before = self.chapter.current_revision

		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, progress="Complete", chapter_status_after="Completed")
		meeting.submit()

		self.chapter.reload()
		self.assertEqual(self.chapter.status, "Completed")
		self.assertEqual(frappe.db.get_value(REVISION, revision_before, "status"), "Completed")

		# A Completed Chapter is not seeded into the next meeting.
		self.assertFalse(make_meeting(self.implementation.name, meeting_date="2026-03-01").chapter_reviews)

		meeting.cancel()
		self.chapter.reload()
		self.assertEqual(self.chapter.status, "Planned")

	def test_a_draft_chapter_cannot_be_completed_directly(self):
		draft = make_chapter(self.implementation.name, title="Draft", plan=False)
		draft.status = "Completed"
		self.assertRaises(frappe.ValidationError, draft.save)

	def test_history_shows_a_chapter_added_while_still_draft(self):
		draft = make_chapter(self.implementation.name, title="Draft Chapter", plan=False)
		meeting = make_meeting(self.implementation.name)
		meeting.append("chapter_reviews", {"chapter": draft.name})
		meeting.save()

		set_as_planned(draft.name)
		meeting.reload()
		set_progress(meeting, decision="Yes")
		meeting.submit()

		revisions = get_chapter_history(draft.name)["revisions"]
		self.assertEqual(revisions[0]["progress"], "On Track")
		self.assertEqual(revisions[0]["decision"], "Yes")

	def test_patch_fills_the_reviewed_revision_on_old_meetings(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting)
		meeting.submit()
		row = meeting.chapter_reviews[0]
		frappe.db.set_value(REVIEW_ROW, row.name, "current_revision", None)

		backfill_reviewed_revision_on_meeting_reviews.execute()

		self.assertEqual(
			frappe.db.get_value(REVIEW_ROW, row.name, "current_revision"), self.chapter.current_revision
		)

	def test_status_only_change_updates_the_current_revision_in_place(self):
		revision_before = self.chapter.current_revision

		meeting = make_meeting(self.implementation.name)
		set_progress(meeting, chapter_status_after="In Progress")
		meeting.submit()

		self.chapter.reload()
		self.assertEqual(self.chapter.status, "In Progress")
		self.assertEqual(self.chapter.current_revision, revision_before)
		self.assertEqual(frappe.db.count(REVISION, {"implementation_chapter": self.chapter.name}), 1)
		self.assertEqual(frappe.db.get_value(REVISION, revision_before, "status"), "In Progress")
		self.assertFalse(
			frappe.db.get_value(REVIEW_ROW, meeting.chapter_reviews[0].name, "previous_revision")
		)

		meeting.reload()
		meeting.cancel()

		self.assertEqual(frappe.db.get_value("Implementation Chapter", self.chapter.name, "status"), "Planned")
		self.assertEqual(frappe.db.get_value(REVISION, revision_before, "status"), "Planned")


class TestStakeholderMeetingCancelRules(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()
		self.chapter = make_chapter(self.implementation.name)

	def test_cancel_refused_when_implementation_edited_after_submit(self):
		meeting = make_meeting(self.implementation.name)
		set_progress(meeting)
		meeting.submit()

		implementation = frappe.get_doc("Implementation", self.implementation.name)
		implementation.next_review_due = "2027-01-01"
		implementation.save()

		meeting.reload()
		self.assertRaises(frappe.ValidationError, meeting.cancel)
		self.assertEqual(frappe.db.get_value("Stakeholder Meeting", meeting.name, "docstatus"), 1)

	def test_revision_numbers_continue_correctly_after_a_cancel(self):
		first = make_meeting(self.implementation.name)
		set_progress(first, current_level=2)
		first.submit()
		first.reload()
		cancelled_revision = first.chapter_reviews[0].current_revision
		self.assertEqual(frappe.db.get_value(REVISION, cancelled_revision, "revision_number"), 2)

		first.cancel()
		self.assertFalse(frappe.db.exists(REVISION, cancelled_revision))

		second = make_meeting(self.implementation.name)
		set_progress(second, current_level=2)
		second.submit()

		self.chapter.reload()
		self.assertEqual(frappe.db.get_value(REVISION, self.chapter.current_revision, "revision_number"), 2)
		self.assertEqual(frappe.db.count(REVISION, {"implementation_chapter": self.chapter.name}), 2)


class TestStakeholderMeetingSeeding(FrappeTestCase):
	def setUp(self):
		self.implementation = make_implementation()

	def test_only_active_chapters_are_seeded(self):
		planned = make_chapter(self.implementation.name, title="Planned")

		in_progress = make_chapter(self.implementation.name, title="In Progress")
		in_progress.status = "In Progress"
		in_progress.save()

		blocked = make_chapter(self.implementation.name, title="Blocked")
		blocked.status = "Blocked"
		blocked.save()

		make_chapter(self.implementation.name, title="Draft", plan=False)

		cancelled = make_chapter(self.implementation.name, title="Cancelled", plan=False)
		cancelled.status = "Cancelled"
		cancelled.save()

		meeting = make_meeting(self.implementation.name)

		self.assertEqual(
			{row.chapter for row in meeting.chapter_reviews},
			{planned.name, in_progress.name, blocked.name},
		)

	def test_picking_an_implementation_fills_rows_before_save(self):
		self.implementation.reload()
		for organisation in ("Internal", "Customer", "Third Party"):
			self.implementation.append(
				"stakeholders",
				{
					"full_name": f"{organisation} Person",
					"email": f"{organisation.replace(' ', '').lower()}@example.com",
					"stakeholder_organisation": organisation,
				},
			)
		self.implementation.save()
		chapter = make_chapter(self.implementation.name)

		meeting = frappe.get_doc(
			{"doctype": "Stakeholder Meeting", "implementation": self.implementation.name}
		)
		meeting.fetch_from_implementation()

		self.assertEqual(
			sorted(row.stakeholder_organisation for row in meeting.attendees), ["Customer", "Internal"]
		)
		row = meeting.chapter_reviews[0]
		self.assertEqual(row.chapter, chapter.name)
		self.assertEqual(str(row.planned_start), "2026-01-01")
		self.assertEqual(str(row.target_date), "2026-06-30")

		# Picking another Implementation replaces the rows.
		other = make_implementation()
		other_chapter = make_chapter(other.name, title="Other")
		meeting.implementation = other.name
		meeting.fetch_from_implementation()
		self.assertFalse(meeting.attendees)
		self.assertEqual([row.chapter for row in meeting.chapter_reviews], [other_chapter.name])

	def test_rows_are_not_refilled_after_the_first_save(self):
		make_chapter(self.implementation.name)
		meeting = make_meeting(self.implementation.name)
		self.assertRaises(frappe.ValidationError, meeting.fetch_from_implementation)

	def test_a_row_added_by_hand_gets_the_chapter_dates(self):
		chapter = make_chapter(self.implementation.name)

		values = get_chapter_review_row(self.implementation.name, chapter.name)
		self.assertEqual(str(values["planned_start"]), "2026-01-01")
		self.assertEqual(str(values["target_date"]), "2026-06-30")
		self.assertEqual(values["current_revision"], chapter.current_revision)
		self.assertEqual(values["chapter_status_before"], "Planned")

		other_chapter = make_chapter(make_implementation().name)
		self.assertRaises(
			frappe.ValidationError, get_chapter_review_row, self.implementation.name, other_chapter.name
		)

	def test_change_since_the_last_submitted_meeting_is_flagged_as_drift(self):
		chapter = make_chapter(self.implementation.name)

		first = make_meeting(self.implementation.name)
		self.assertFalse(first.chapter_reviews[0].drift_detected)
		set_progress(first)
		first.submit()

		chapter.reload()
		chapter.current_level = 2
		chapter.save()

		second = make_meeting(self.implementation.name, meeting_date="2026-03-01")
		row = second.chapter_reviews[0]
		self.assertTrue(row.drift_detected)
		self.assertIn("Current Level: 1 → 2", row.drift_details)


class TestStakeholderMeetingPermissions(FrappeTestCase):
	def test_only_system_manager_can_submit_meetings(self):
		permissions = frappe.get_meta("Stakeholder Meeting").permissions
		self.assertEqual({perm.role for perm in permissions if perm.submit}, {"System Manager"})
		self.assertFalse([perm for perm in permissions if perm.role == "All"])

	def test_all_role_can_only_read_meeting_types(self):
		permissions = [perm for perm in frappe.get_meta("Meeting Type").permissions if perm.role == "All"]
		self.assertEqual(len(permissions), 1)
		self.assertTrue(permissions[0].read)
		self.assertFalse(permissions[0].create or permissions[0].write or permissions[0].delete)


class TestConnectionLinks(FrappeTestCase):
	"""The Connections tab counts links with `link_fieldname`; a missing or wrong
	field breaks the form's dashboard query."""

	DOCTYPES = (
		"Implementation",
		"Implementation Chapter",
		"Implementation Chapter Revision",
		"Stakeholder Meeting",
	)

	def test_every_link_field_exists_on_the_linked_doctype(self):
		for doctype in self.DOCTYPES:
			for link in frappe.get_meta(doctype).links:
				with self.subTest(doctype=doctype, link_doctype=link.link_doctype):
					self.assertTrue(link.link_fieldname)
					self.assertTrue(frappe.get_meta(link.link_doctype).has_field(link.link_fieldname))

	def test_meetings_are_linked_through_the_chapter_review_table(self):
		for doctype, link_fieldname in (
			("Implementation Chapter", "chapter"),
			("Implementation Chapter Revision", "current_revision"),
		):
			with self.subTest(doctype=doctype):
				links = [
					link for link in frappe.get_meta(doctype).links if link.link_doctype == REVIEW_ROW
				]
				self.assertEqual(len(links), 1)
				self.assertTrue(links[0].is_child_table)
				self.assertEqual(links[0].parent_doctype, "Stakeholder Meeting")
				self.assertEqual(links[0].table_fieldname, "chapter_reviews")
				self.assertEqual(links[0].link_fieldname, link_fieldname)
				self.assertEqual(frappe.get_meta(REVIEW_ROW).get_field(link_fieldname).options, doctype)
