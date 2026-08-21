# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import formatdate

ATTENDEE_ORGANISATIONS = ("Internal", "Customer")
CHAPTER_REVIEW_STATUSES = ("Planned", "In Progress", "Blocked")


class StakeholderMeeting(Document):
	def before_insert(self):
		self.seed_attendees_from_implementation()
		self.seed_chapter_reviews_from_implementation()

	def before_submit(self):
		missing = [row.chapter_title or row.chapter for row in self.chapter_reviews if not row.progress]
		if missing:
			frappe.throw(
				frappe._("Please set Progress for every Chapter Review before submitting: {0}").format(
					", ".join(missing)
				)
			)

	def on_submit(self):
		self.sync_chapter_reviews_to_chapters()

	def sync_chapter_reviews_to_chapters(self):
		"""Write the agreed operational fields captured on each Chapter Review row
		back onto its Chapter: current/target level, the optional proposed status,
		and last-reviewed metadata. This only touches operational fields - it never
		creates a Chapter Revision or changes agreed content prose.

		Saving the Chapter cascades into an Implementation.save() (to mirror the
		module row), which would otherwise also log a new Implementation status
		history entry for today. That history is meant to capture deliberate
		Implementation-level status entries, not a side effect of a meeting, so it
		is suppressed for the duration of this sync via frappe.flags."""
		frappe.flags.in_stakeholder_meeting_submit = True
		try:
			for row in self.chapter_reviews:
				if not row.chapter:
					continue

				chapter = frappe.get_doc("Implementation Chapter", row.chapter)
				chapter.current_level = row.current_level
				chapter.target_level = row.target_level
				if row.chapter_status_after:
					chapter.status = row.chapter_status_after
				chapter.last_meeting = self.name
				chapter.last_reviewed_on = self.meeting_date
				chapter.save(ignore_permissions=True)
		finally:
			frappe.flags.in_stakeholder_meeting_submit = False

	def seed_attendees_from_implementation(self):
		"""Snapshot the Implementation's Internal and Customer stakeholders as
		attendee rows. Third Party stakeholders are skipped. Runs once, on
		creation, so the chair can freely remove rows afterwards without them
		being re-added on a later save."""
		if not self.implementation or self.attendees:
			return

		stakeholders = frappe.get_all(
			"Implementation Stakeholder",
			filters={"parent": self.implementation, "parenttype": "Implementation"},
			fields=[
				"contact",
				"full_name",
				"email",
				"stakeholder_organisation",
				"stakeholder_type",
				"stakeholder_position",
			],
		)
		for stakeholder in stakeholders:
			if stakeholder.stakeholder_organisation not in ATTENDEE_ORGANISATIONS:
				continue
			self.append("attendees", stakeholder)

	def seed_chapter_reviews_from_implementation(self):
		"""Seed one review row per Planned/In Progress/Blocked Chapter, pinned to
		that Chapter's current revision and current/target level at the time of
		the meeting. Runs once, on creation; the chair can remove seeded rows
		and add other Chapters manually afterwards."""
		if not self.implementation or self.chapter_reviews:
			return

		chapters = frappe.get_all(
			"Implementation Chapter",
			filters={"implementation": self.implementation, "status": ["in", CHAPTER_REVIEW_STATUSES]},
			fields=[
				"name",
				"chapter_title",
				"current_revision",
				"status",
				"current_level",
				"target_level",
				"planned_start",
				"target_date",
				"last_meeting",
				"last_reviewed_on",
			],
		)
		for chapter in chapters:
			drift_detected, drift_details = self.detect_chapter_drift(chapter)
			self.append(
				"chapter_reviews",
				{
					"chapter": chapter.name,
					"chapter_title": chapter.chapter_title,
					"current_revision": chapter.current_revision,
					"chapter_status_before": chapter.status,
					"current_level": chapter.current_level,
					"target_level": chapter.target_level,
					"planned_start": chapter.planned_start,
					"target_date": chapter.target_date,
					"drift_detected": drift_detected,
					"drift_details": drift_details,
				},
			)

	def detect_chapter_drift(self, chapter):
		"""Compare this Chapter's live levels, status, and planned dates to the
		snapshot recorded on its own last submitted Stakeholder Meeting review
		row, so the PM can explain what changed between customer reviews. A
		Chapter with no prior submitted meeting has nothing to drift from and is
		never flagged."""
		if not chapter.last_meeting:
			return 0, ""

		last_row = frappe.db.get_value(
			"Stakeholder Meeting Chapter Review",
			{"parent": chapter.last_meeting, "chapter": chapter.name},
			[
				"current_level",
				"target_level",
				"chapter_status_after",
				"chapter_status_before",
				"planned_start",
				"target_date",
			],
			as_dict=True,
		)
		if not last_row:
			return 0, ""

		last_status = last_row.chapter_status_after or last_row.chapter_status_before

		changes = []
		if chapter.current_level != last_row.current_level:
			changes.append(
				frappe._("Current Level: {0} → {1}").format(last_row.current_level, chapter.current_level)
			)
		if chapter.target_level != last_row.target_level:
			changes.append(
				frappe._("Target Level: {0} → {1}").format(last_row.target_level, chapter.target_level)
			)
		if last_status and chapter.status != last_status:
			changes.append(frappe._("Status: {0} → {1}").format(last_status, chapter.status))
		if chapter.planned_start != last_row.planned_start:
			changes.append(
				frappe._("Planned Start: {0} → {1}").format(
					formatdate(last_row.planned_start) if last_row.planned_start else "-",
					formatdate(chapter.planned_start) if chapter.planned_start else "-",
				)
			)
		if chapter.target_date != last_row.target_date:
			changes.append(
				frappe._("Target Date: {0} → {1}").format(
					formatdate(last_row.target_date) if last_row.target_date else "-",
					formatdate(chapter.target_date) if chapter.target_date else "-",
				)
			)

		if not changes:
			return 0, ""

		last_reviewed = formatdate(chapter.last_reviewed_on) if chapter.last_reviewed_on else None
		heading = (
			frappe._("Changed since the last submitted meeting on {0}:").format(last_reviewed)
			if last_reviewed
			else frappe._("Changed since the last submitted meeting:")
		)
		return 1, heading + " " + "; ".join(changes)
