# Copyright (c) 2025, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class RecruitmentSettings(Document):
	def get_interview_config(self, job_opening, interview_round=None):
		if not job_opening:
			frappe.throw(
				_("Job Opening is required to get interview configuration"),
				exc=frappe.ValidationError
			)
		
		config = None
		for row in self.job_opening_configs:
			if row.job_opening == job_opening:
				if interview_round and row.interview_round != interview_round:
					continue
				
				config = {
					"interview_round": row.interview_round,
					"sender": self.sender,
					"sender_email": self.sender_email,
					"interview_confirmation": self.interview_confirmation or row.interview_confirmation,
					"interviewers": []
				}
				
				interviewers = frappe.get_all(
					"Interviewer",
					filters={"parent": row.interview_round, "parenttype": "Interview Round"},
					fields=["user"]
				)
				
				if not interviewers:
					interviewers = []
					for interviewer in self.interviewers:
						interviewers.append({"user": interviewer.user})
				
				config["interviewers"] = interviewers
				break
		
		if not config:
			error_msg = _("No interview configuration found for Job Opening: {0}").format(
				frappe.bold(job_opening)
			)
			if interview_round:
				error_msg += _(" and Interview Round: {0}").format(frappe.bold(interview_round))
			error_msg += _(". Please configure in Recruitment Settings.")
			
			frappe.throw(error_msg, exc=frappe.ValidationError)
		
		return config
