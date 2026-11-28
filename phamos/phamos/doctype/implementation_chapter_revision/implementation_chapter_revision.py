# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ImplementationChapterRevision(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw(frappe._("Implementation Chapter Revisions are immutable and cannot be edited."))

	def on_trash(self):
		# Cancelling the Stakeholder Meeting that created a Revision is the only way to remove it.
		if frappe.flags.in_stakeholder_meeting_cancel:
			return
		frappe.throw(frappe._("Implementation Chapter Revisions are immutable and cannot be deleted."))
