# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class InterviewBookingSlot(Document):
	def set_title(self):
		if self.day_of_week and self.from_time and self.to_time:
			self.title = f"{self.day_of_week} {self.from_time} - {self.to_time}"
