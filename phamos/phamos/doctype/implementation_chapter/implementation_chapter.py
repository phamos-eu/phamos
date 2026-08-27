# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

AGREED_CONTENT_FIELDS = (
	"chapter_title",
	"chapter_introduction",
	"full_chapter_description",
	"planned_start",
	"target_date",
)

REQUIRED_TO_PLAN = (
	"chapter_title",
	"full_chapter_description",
	"planned_start",
	"target_date",
)


class ImplementationChapter(Document):
	def validate(self):
		self.validate_duplicate_chapter_title()
		self.validate_status_transition()
		self.validate_agreed_content_locked()
		self.validate_target_date_after_planned_start()

	def on_update(self):
		self.sync_module_row_in_implementation()

	def sync_module_row_in_implementation(self):
		"""Mirror this Chapter onto its row in the parent Implementation's Modules
		table right away, instead of waiting for someone to open and save the
		Implementation by hand. Reuses the Implementation's own sync methods so a
		brand-new Chapter gets its row created (with Is Required checked) and an
		edited Chapter's levels/dates are pushed through immediately."""
		if not self.implementation:
			return

		frappe.get_doc("Implementation", self.implementation).save(ignore_permissions=True)

	def validate_duplicate_chapter_title(self):
		if not self.implementation or not self.chapter_title:
			return

		duplicate = frappe.db.exists(
			"Implementation Chapter",
			{
				"implementation": self.implementation,
				"chapter_title": self.chapter_title,
				"name": ["!=", self.name or ""],
			},
		)
		if duplicate:
			frappe.throw(
				frappe._(
					"A Chapter titled {0} already exists for this {1}. "
					"Chapter titles must be unique within the same Implementation."
				).format(frappe.bold(self.chapter_title), frappe.bold(self.implementation))
			)

	def validate_status_transition(self):
		"""v1 rule: no un-plan. Draft -> Planned may only happen through the
		"Set as Planned" action (which sets current_revision before saving).
		Once Planned, the Chapter may move between Planned / In Progress /
		Blocked (execution status, not agreed content) or terminate as
		Cancelled, but can never go back to Draft."""
		if self.is_new():
			return

		doc_before_save = self.get_doc_before_save()
		if not doc_before_save or doc_before_save.status == self.status:
			return

		previous_status = doc_before_save.status

		if previous_status == "Cancelled":
			frappe.throw(frappe._("A Cancelled Chapter's status cannot be changed."))

		if self.status == "Draft":
			frappe.throw(frappe._("A Chapter cannot be reverted back to Draft once it has left Draft."))

		if previous_status == "Draft":
			if self.status != "Planned":
				frappe.throw(
					frappe._("A Draft Chapter can only move to Planned or Cancelled, not directly to {0}.").format(
						self.status
					)
				)
			if not self.current_revision:
				frappe.throw(
					frappe._('Use the "Set as Planned" action to move a Chapter from Draft to Planned.')
				)

	def validate_target_date_after_planned_start(self):
		if not self.planned_start or not self.target_date:
			return

		if self.target_date <= self.planned_start:
			frappe.throw(frappe._("Target Date must be after Planned Start."))

	def validate_agreed_content_locked(self):
		"""Once a Chapter leaves Draft, its agreed content is frozen. The only way
		to change it going forward is a future revision workflow (Stakeholder
		Meeting), not a direct edit on the Chapter."""
		if self.is_new():
			return

		doc_before_save = self.get_doc_before_save()
		if not doc_before_save or doc_before_save.status == "Draft":
			return

		changed_labels = []
		for fieldname in AGREED_CONTENT_FIELDS:
			current_value = self.get(fieldname)
			previous_value = doc_before_save.get(fieldname)
			if self.meta.get_field(fieldname).fieldtype in ("Date", "Datetime"):
				current_value = getdate(current_value) if current_value else current_value
				previous_value = getdate(previous_value) if previous_value else previous_value
			if current_value != previous_value:
				changed_labels.append(self.meta.get_label(fieldname))

		if changed_labels:
			frappe.throw(
				frappe._(
					"This Chapter is {0}. Agreed content ({1}) can no longer be edited directly."
				).format(frappe.bold(self.status), ", ".join(changed_labels))
			)


@frappe.whitelist()
def set_as_planned(name):
	"""Freeze the Chapter's current agreed content as an immutable Revision 1
	and move the Chapter from Draft to Planned."""
	doc = frappe.get_doc("Implementation Chapter", name)

	if doc.status != "Draft":
		frappe.throw(frappe._("Only Draft chapters can be set as Planned."))

	missing_labels = [
		doc.meta.get_label(fieldname) for fieldname in REQUIRED_TO_PLAN if not doc.get(fieldname)
	]
	if missing_labels:
		frappe.throw(
			frappe._("Please fill in the following before setting this Chapter as Planned: {0}").format(
				", ".join(missing_labels)
			)
		)

	next_revision_number = (
		frappe.db.count("Implementation Chapter Revision", {"implementation_chapter": doc.name}) + 1
	)

	revision = frappe.get_doc(
		{
			"doctype": "Implementation Chapter Revision",
			"implementation_chapter": doc.name,
			"revision_number": next_revision_number,
			"chapter_title": doc.chapter_title,
			"chapter_introduction": doc.chapter_introduction,
			"full_chapter_description": doc.full_chapter_description,
			"planned_start": doc.planned_start,
			"target_date": doc.target_date,
		}
	)
	revision.insert(ignore_permissions=True)

	doc.current_revision = revision.name
	doc.status = "Planned"
	doc.save(ignore_permissions=True)

	frappe.msgprint(
		frappe._("Created {0} and set it as the current revision of {1}.").format(
			frappe.utils.get_link_to_form("Implementation Chapter Revision", revision.name),
			frappe.utils.get_link_to_form("Implementation Chapter", doc.name),
		),
		title=frappe._("Chapter Planned"),
		indicator="green",
	)

	return {"status": doc.status, "current_revision": doc.current_revision}


@frappe.whitelist()
def get_chapter_history(chapter):
	"""Read-only history for the Chapter's History tab: the revision sequence
	and the submitted Stakeholder Meetings (with their outcomes and any linked
	Decisions) that reviewed this Chapter. Built entirely from Implementation
	Chapter Revision / Stakeholder Meeting Chapter Review / Stakeholder Meeting
	Decision - never touches Implementation.status_updates."""
	doc = frappe.get_doc("Implementation Chapter", chapter)

	revisions = frappe.get_all(
		"Implementation Chapter Revision",
		filters={"implementation_chapter": chapter},
		fields=[
			"name",
			"revision_number",
			"chapter_title",
			"chapter_introduction",
			"planned_start",
			"target_date",
			"creation",
		],
		order_by="revision_number asc",
	)
	for revision in revisions:
		revision["is_current"] = revision.name == doc.current_revision

	review_rows = frappe.get_all(
		"Stakeholder Meeting Chapter Review",
		filters={"chapter": chapter, "docstatus": 1},
		fields=[
			"parent",
			"progress",
			"scope_change",
			"chapter_status_before",
			"chapter_status_after",
			"previous_revision",
			"current_revision",
		],
	)
	reviews_by_meeting = {row.parent: row for row in review_rows}

	meetings = []
	if reviews_by_meeting:
		meeting_rows = frappe.get_all(
			"Stakeholder Meeting",
			filters={"name": ["in", list(reviews_by_meeting.keys())], "docstatus": 1},
			fields=["name", "meeting_date", "meeting_type", "chair"],
			order_by="meeting_date desc, creation desc",
		)

		decision_rows = frappe.get_all(
			"Stakeholder Meeting Decision",
			filters={"chapter": chapter, "docstatus": 1},
			fields=["parent", "decision_type", "decision", "subject", "effective_date", "notes"],
		)
		decisions_by_meeting = {}
		for decision in decision_rows:
			decisions_by_meeting.setdefault(decision.parent, []).append(decision)

		for meeting in meeting_rows:
			review = reviews_by_meeting.get(meeting.name, {})
			meeting["progress"] = review.get("progress")
			meeting["scope_change"] = review.get("scope_change")
			meeting["chapter_status_before"] = review.get("chapter_status_before")
			meeting["chapter_status_after"] = review.get("chapter_status_after")
			meeting["previous_revision"] = review.get("previous_revision")
			meeting["current_revision"] = review.get("current_revision")
			meeting["decisions"] = decisions_by_meeting.get(meeting.name, [])
			meetings.append(meeting)

	return {
		"current_revision": doc.current_revision,
		"revisions": revisions,
		"meetings": meetings,
	}
