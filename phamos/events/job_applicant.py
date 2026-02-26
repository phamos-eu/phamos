from frappe import _
import frappe
from hrms.hr.doctype.job_applicant.job_applicant import JobApplicant
from frappe.email.doctype.notification.notification import evaluate_alert


class CustomJobApplicant(JobApplicant):
	@frappe.whitelist()
	def invite_for_interview(self, interview_round=None):
		if not self.custom_available_slots:
			frappe.throw(_("Please select a slot in Available Slots table"))
		
		if not interview_round:
			frappe.throw(_("Interview Round is required"))
		
		# Validate interview configuration exists for this job opening and interview round
		if self.job_title:
			settings = frappe.get_single("Recruitment Settings")
			config = settings.get_interview_config(self.job_title, interview_round)
			
			if not config.get("interview_round"):
				frappe.throw(
					_("Interview Round {0} not configured for Job Opening: {1}. Please configure in Recruitment Settings.").format(
						frappe.bold(interview_round),
						frappe.bold(self.job_title)
					)
				)

		notification = "Job interview Slot Booking"
		evaluate_alert(self, notification, "Custom")
		if not self.custom_shortlisted or self.custom_shortlisted == "No":
			self.db_set("custom_shortlisted", "Yes")
			return {"custom_shortlisted": "Yes"}
