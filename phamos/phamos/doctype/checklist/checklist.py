# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Checklist(Document):
	def validate(self):
		self.set_completion_percentage_and_status()


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