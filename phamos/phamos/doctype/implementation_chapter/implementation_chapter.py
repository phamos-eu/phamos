# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

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
		"Set as Planned" action (which sets current_revision before saving);
		a Planned/Cancelled Chapter can never go back to Draft."""
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

		if previous_status == "Draft" and self.status == "Planned" and not self.current_revision:
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

		changed_labels = [
			self.meta.get_label(fieldname)
			for fieldname in AGREED_CONTENT_FIELDS
			if self.get(fieldname) != doc_before_save.get(fieldname)
		]
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

	return {"status": doc.status, "current_revision": doc.current_revision}
