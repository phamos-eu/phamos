# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import formatdate

from phamos.phamos.doctype.implementation.implementation import compute_next_review_due
from phamos.phamos.doctype.implementation_chapter.implementation_chapter import create_revision_snapshot

ATTENDEE_ORGANISATIONS = ("Internal", "Customer")
CHAPTER_REVIEW_STATUSES = ("Planned", "In Progress", "Blocked")
PROPOSED_CONTENT_REQUIRED = (
	"proposed_chapter_title",
	"proposed_full_chapter_description",
	"proposed_planned_start",
	"proposed_target_date",
)


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
		self.validate_proposed_content_for_scope_changes()

	def validate_proposed_content_for_scope_changes(self):
		"""A Chapter Review flagged with Scope Change must have its proposed
		content filled in before submit, since that content becomes the new
		Chapter Revision."""
		review_meta = frappe.get_meta("Stakeholder Meeting Chapter Review")
		for row in self.chapter_reviews:
			if not row.scope_change:
				continue

			missing_labels = [
				review_meta.get_label(fieldname)
				for fieldname in PROPOSED_CONTENT_REQUIRED
				if not row.get(fieldname)
			]
			if missing_labels:
				frappe.throw(
					frappe._(
						"Please fill in the following proposed content for the Scope Change on Chapter {0}: {1}"
					).format(row.chapter_title or row.chapter, ", ".join(missing_labels))
				)

	def on_submit(self):
		"""Saving a Chapter (in sync_chapter_reviews_to_chapters) and saving the
		Implementation (in advance_implementation_review_cadence) both cascade
		into an Implementation.save(), which would otherwise log a new
		Implementation status history entry for today. That history is meant to
		capture deliberate Implementation-level status entries, not a side
		effect of a meeting, so it is suppressed for this whole submit via
		frappe.flags."""
		frappe.flags.in_stakeholder_meeting_submit = True
		try:
			self.sync_chapter_reviews_to_chapters()
			self.advance_implementation_review_cadence()
		finally:
			frappe.flags.in_stakeholder_meeting_submit = False

	def sync_chapter_reviews_to_chapters(self):
		created_revisions = []
		for row in self.chapter_reviews:
			if not row.chapter:
				continue

			chapter = frappe.get_doc("Implementation Chapter", row.chapter)
			level_changed = (
				row.current_level != chapter.current_level or row.target_level != chapter.target_level
			)
			chapter.current_level = row.current_level
			chapter.target_level = row.target_level
			if row.chapter_status_after:
				chapter.status = row.chapter_status_after
			chapter.last_meeting = self.name
			chapter.last_reviewed_on = self.meeting_date
			if row.decision:
				chapter.decision = row.decision
			if row.decision_description:
				chapter.decision_description = row.decision_description

			new_revision_name = None
			if row.scope_change:
				new_revision_name = self.create_chapter_revision_from_row(chapter, row)
				chapter.chapter_title = row.proposed_chapter_title
				chapter.chapter_introduction = row.proposed_chapter_introduction
				chapter.full_chapter_description = row.proposed_full_chapter_description
				chapter.planned_start = row.proposed_planned_start
				chapter.target_date = row.proposed_target_date
			elif level_changed:
				new_revision_name = create_revision_snapshot(chapter).name

			if new_revision_name:
				chapter.current_revision = new_revision_name

			chapter.save(ignore_permissions=True)

			if new_revision_name:
				row.db_set(
					{"previous_revision": row.current_revision, "current_revision": new_revision_name},
					update_modified=False,
				)
				created_revisions.append((chapter.name, new_revision_name))

		self.notify_created_revisions(created_revisions)

	def advance_implementation_review_cadence(self):
		"""Record this submitted meeting as the Implementation's latest review
		and, if a Review Cadence is configured, push Next Review Due forward
		from this meeting's date. Only ever runs off an actual submit - nothing
		here runs on a schedule, so overdue only ever clears through a real
		review, and a later calendar integration remains free to own actual
		scheduling."""
		if not self.implementation:
			return

		implementation = frappe.get_doc("Implementation", self.implementation)
		implementation.last_stakeholder_meeting = self.name
		implementation.last_reviewed_on = self.meeting_date
		if implementation.review_cadence:
			implementation.next_review_due = compute_next_review_due(
				self.meeting_date, implementation.review_cadence
			)
		implementation.save(ignore_permissions=True)

	def notify_created_revisions(self, created_revisions):
		"""Tell the chair what this submit actually created, with links, instead
		of the meeting appearing to submit silently."""
		if not created_revisions:
			return

		lines = [
			frappe._("{0} → new revision {1}").format(
				frappe.utils.get_link_to_form("Implementation Chapter", chapter_name),
				frappe.utils.get_link_to_form("Implementation Chapter Revision", revision_name),
			)
			for chapter_name, revision_name in created_revisions
		]
		frappe.msgprint(
			"<br>".join(lines),
			title=frappe._("Chapter Revisions Created"),
			indicator="green",
		)

	def create_chapter_revision_from_row(self, chapter, row):
		"""Freeze this Chapter Review row's proposed content as the next
		immutable Chapter Revision. Mirrors set_as_planned()'s revision creation,
		but sourced from the agreed proposal captured in this meeting instead of
		the Chapter's own (locked) fields."""
		next_revision_number = (
			frappe.db.count("Implementation Chapter Revision", {"implementation_chapter": chapter.name}) + 1
		)
		revision = frappe.get_doc(
			{
				"doctype": "Implementation Chapter Revision",
				"implementation_chapter": chapter.name,
				"revision_number": next_revision_number,
				"status": chapter.status,
				"target_level": chapter.target_level,
				"current_level": chapter.current_level,
				"chapter_title": row.proposed_chapter_title,
				"chapter_introduction": row.proposed_chapter_introduction,
				"full_chapter_description": row.proposed_full_chapter_description,
				"planned_start": row.proposed_planned_start,
				"target_date": row.proposed_target_date,
			}
		)
		revision.insert(ignore_permissions=True)
		return revision.name

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
