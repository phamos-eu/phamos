# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.exceptions import TimestampMismatchError


class Checklist(Document):
	def validate(self):
		self.validate_checklist_owner()
		self.set_completion_percentage_and_status()

	def validate_checklist_owner(self):
		if not self.checklist_owner:
			frappe.throw(frappe._("Checklist Owner is required"))

		if not frappe.db.exists("User", self.checklist_owner):
			frappe.throw(frappe._("Checklist Owner must be a valid User"))

		if frappe.db.get_value("User", self.checklist_owner, "enabled") == 0:
			frappe.throw(frappe._("Checklist Owner must be an enabled User"))

	def set_completion_percentage_and_status(self):
		if not self.checklist_items:
			self.completion_percentage = 0
			self.status = "Not Started"
			return

		total_items = len(self.checklist_items)
		completed_items = sum(1 for item in self.checklist_items if item.done)

		self.completion_percentage = (completed_items / total_items) * 100

		if completed_items == 0:
			self.status = "Not Started"
		elif completed_items == total_items:
			self.status = "Completed"
		else:
			self.status = "In Progress"


@frappe.whitelist()
def get_checklist_details(checklist_name):
	checklist = frappe.get_doc("Checklist", checklist_name)
	checklist.check_permission("read")

	items = []
	for row in checklist.checklist_items:
		items.append(
			{
				"name": row.name,
				"idx": row.idx,
				"done": row.done,
				"note": row.note,
				"document": row.document,
				"record": row.record,
			}
		)

	return {
		"name": checklist.name,
		"status": checklist.status,
		"completion_percentage": checklist.completion_percentage or 0,
		"items": items,
	}


@frappe.whitelist()
def update_checklist_item(checklist_name, item_name, values):
	if isinstance(values, str):
		values = frappe.parse_json(values)

	if not isinstance(values, dict):
		frappe.throw(frappe._("Invalid checklist item payload"))

	allowed_fields = {"done", "note", "document", "record"}
	invalid_fields = [field for field in values.keys() if field not in allowed_fields]
	if invalid_fields:
		frappe.throw(frappe._("Unsupported fields: {0}").format(", ".join(invalid_fields)))

	def apply_values(target_row):
		if "document" in values:
			target_row.document = values.get("document") or None
			if not target_row.document:
				target_row.record = None

		if "record" in values:
			target_row.record = values.get("record") or None

		if "note" in values:
			target_row.note = values.get("note") or ""

		if "done" in values:
			target_row.done = 1 if frappe.utils.cint(values.get("done")) else 0

	last_error = None
	checklist = None
	row = None

	for _ in range(3):
		try:
			checklist = frappe.get_doc("Checklist", checklist_name)
			checklist.check_permission("write")

			row = None
			for checklist_row in checklist.checklist_items:
				if checklist_row.name == item_name:
					row = checklist_row
					break

			if not row:
				frappe.throw(frappe._("Checklist item not found"))

			apply_values(row)
			checklist.save()
			last_error = None
			break
		except TimestampMismatchError as exc:
			last_error = exc
			frappe.db.rollback()

	if last_error:
		raise last_error

	return {
		"status": checklist.status,
		"completion_percentage": checklist.completion_percentage or 0,
		"item": {
			"name": row.name,
			"done": row.done,
			"note": row.note,
			"document": row.document,
			"record": row.record,
		},
	}