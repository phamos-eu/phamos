# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ChecklistTemplate(Document):
	def validate(self):
		if not self.checklist_template_items:
			frappe.throw(_("Please add at least one Checklist Template Item"))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def checklist_template_owner_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link search: enabled Users that have the Employee role."""
	return frappe.db.sql(
		"""
		select distinct u.name, u.full_name
		from `tabUser` u
		inner join `tabHas Role` hr
			on hr.parent = u.name and hr.parenttype = 'User'
		where hr.role = 'Employee'
			and u.enabled = 1
			and u.name != 'Guest'
			and (
				u.name like %(txt)s
				or ifnull(u.full_name, '') like %(txt)s
			)
		order by u.name
		limit %(start)s, %(page_len)s
		""",
		{"txt": f"%{txt}%", "start": start, "page_len": page_len},
	)


@frappe.whitelist()
def create_checklist_from_template(template_name, checklist_name=None, reference_record=None):
	"""Snapshot template items into a new Checklist. Reference Record is optional."""
	if not template_name:
		frappe.throw(_("Checklist Template is required"))

	template = frappe.get_doc("Checklist Template", template_name)
	template.check_permission("read")

	if template.docstatus != 1:
		frappe.throw(_("Only submitted Checklist Templates can create Checklists"))

	if not template.checklist_template_items:
		frappe.throw(_("Checklist Template has no items to copy"))

	checklist_name = (checklist_name or "").strip() or template.name
	if frappe.db.exists("Checklist", checklist_name):
		frappe.throw(_("Checklist {0} already exists").format(checklist_name))

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
			"name": checklist_name,
			"document": template.document,
			"reference_record": reference_record,
			"checklist_template": template.name,
		}
	)

	for item in template.checklist_template_items:
		checklist.append(
			"checklist_items",
			{
				"note": item.note,
				"document": item.document,
				"record": item.record,
				"done": 0,
			},
		)

	checklist.insert()
	return checklist.name
