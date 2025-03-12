from frappe import _
import frappe
from hrms.hr.doctype.job_applicant.job_applicant import create_interview
from frappe.rate_limiter import rate_limit
no_cache = 1


def get_context(context):
	applicant_id = frappe.form_dict.get("name")

	if not frappe.db.exists("Job Applicant", applicant_id):
		return {"status": "error", "message": "Job Applicant not found"}

	context.job_applicant = frappe.db.get_value("Job Applicant", applicant_id, ["applicant_name", "custom_interview_booking_slot"], as_dict=1)
	return context


@frappe.whitelist(allow_guest=True)
# @rate_limit(limit=1, seconds=60)
def schedule_interview(applicant_id, interview_date, interview_slot):
	try:
		if not frappe.db.exists("Job Applicant", applicant_id):
			return {"status": "error", "message": "Job Applicant not found"}

		applicant_doc = frappe.get_doc("Job Applicant", applicant_id)
		applicant_doc.custom_shortlisted = "Yes"
		applicant_doc.save(ignore_permissions=True)

		interview_slot_doc = frappe.get_doc("Interview Booking Slot", interview_slot)

		interview_round = frappe.get_single("Recruitment Settings").interview_round
		if not interview_round:
			raise Exception(_("Interview Round is not set in Recruitment Settings"))

		interviewers = frappe.get_all("Assignment Rule User", filters={"parent": "Recruitment Settings"}, fields=["user"])

		interview = create_interview(applicant_doc, interview_round)
		interview.scheduled_on = interview_date
		interview.from_time = interview_slot_doc.from_time
		interview.to_time = interview_slot_doc.to_time
		if interviewers:
			interview.interview_details = []
			interview.append("interview_details", {
				"interviewer": interviewers[0].user,
			})

		interview.save(ignore_permissions=True)
		return {"status": "success"}

	except Exception as e:
		frappe.log_error(f"Interview Scheduling Error: {str(e)}", "Schedule Interview")
		return {"status": "error", "message": str(e)}


@frappe.whitelist(allow_guest=True)
def get_available_slots():
	slots_dict = {}

	interview_slots = frappe.get_all(
		"Interview Booking Slots",
		filters={"parent": "Recruitment Settings"},
		fields=["day_of_week", "from_time", "to_time"]
	)	
	for slot in interview_slots: 
		day = slot.day_of_week
		slot_time = f"{day} {slot.from_time} - {slot.to_time}" 
		
		if day not in slots_dict:
			slots_dict[day] = []
		
		slots_dict[day].append(slot_time)

	formatted_slots = [{day: times} for day, times in slots_dict.items()]

	return formatted_slots