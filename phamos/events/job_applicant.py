from frappe import _
import frappe
from hrms.hr.doctype.job_applicant.job_applicant import JobApplicant
from frappe.email.doctype.notification.notification import evaluate_alert


class CustomJobApplicant(JobApplicant):
	@frappe.whitelist()
	def invite_for_interview(self):
		notification = "Job interview Slot Booking"
		evaluate_alert(self, notification, "Custom")
		if not self.custom_shortlisted or self.custom_shortlisted == "No":
			self.db_set("custom_shortlisted", "Yes")
			return {"custom_shortlisted": "Yes"}
