# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class Implementation(Document):
	def before_save(self):
		self.remove_duplicate_rows_of_status_history()

	def remove_duplicate_rows_of_status_history(self):
		unique_items = set()
		new_items = []

		for row in self.status_information:  # Replace 'items' with your child table fieldname
			if row.time not in unique_items:
				unique_items.add(row.time)
				new_items.append(row)

		self.status_information = new_items
		#self.save(ignore_permissions=True)
