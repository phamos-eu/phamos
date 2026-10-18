# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, today


class ChecklistTemplate(Document):
	def validate(self):
		if not self.checklist_template_items:
			frappe.throw(_("Please add at least one Checklist Template Item"))

		from phamos.phamos.doctype.checklist.checklist_assignment import validate_assignees

		assignees = {item.assigned_to for item in self.checklist_template_items if item.get("assigned_to")}
		if assignees:
			validate_assignees(assignees)


@frappe.whitelist()
def create_checklist_from_template(
	template_name, title=None, reference_record=None, checklist_owner=None
):
	"""Snapshot template items into a new Checklist owned by `checklist_owner` (required).

	Reference Record is optional. Returns the name of the new Checklist.
	"""
	if not template_name:
		frappe.throw(_("Checklist Template is required"))

	checklist_owner = (checklist_owner or "").strip()
	if not checklist_owner:
		frappe.throw(_("Checklist Owner is required"))

	template = frappe.get_doc("Checklist Template", template_name)
	template.check_permission("read")

	if template.docstatus != 1:
		frappe.throw(_("Only submitted Checklist Templates can create Checklists"))

	if not template.checklist_template_items:
		frappe.throw(_("Checklist Template has no items to copy"))

	title = (title or "").strip() or template.title or template.name

	reference_record = (reference_record or "").strip() or None
	if reference_record:
		if not template.document:
			frappe.throw(_("Checklist Template has no Document type set"))
		if not frappe.db.exists(template.document, reference_record):
			frappe.throw(
				_("{0} {1} does not exist").format(template.document, reference_record)
			)

	checklist = frappe.get_doc(
		{
			"doctype": "Checklist",
			"naming_series": "CHK-.####",
			"title": title,
			"document": template.document,
			"reference_record": reference_record,
			"checklist_template": template.name,
			"checklist_owner": checklist_owner,
		}
	)

	for item in template.checklist_template_items:
		checklist.append(
			"checklist_items",
			{
				"description": item.description,
				"note": item.note,
				"document": item.document,
				"record": item.record,
				"done": 0,
				"assigned_to": item.get("assigned_to") or None,
				"due_date": template_item_due_date(item),
			},
		)

	checklist.insert()
	return checklist.name


def template_item_due_date(item):
	"""`due_in_days` counts from the day the checklist is created; 0 means no due date (#1625)."""
	days = cint(item.get("due_in_days"))
	return add_days(today(), days) if days > 0 else None
