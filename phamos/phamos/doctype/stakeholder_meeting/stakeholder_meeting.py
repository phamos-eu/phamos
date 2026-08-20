# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

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
			fields=["name", "chapter_title", "current_revision", "current_level", "target_level"],
		)
		for chapter in chapters:
			self.append(
				"chapter_reviews",
				{
					"chapter": chapter.name,
					"chapter_title": chapter.chapter_title,
					"current_revision": chapter.current_revision,
					"current_level": chapter.current_level,
					"target_level": chapter.target_level,
				},
			)
