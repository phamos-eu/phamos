from frappe import _
import frappe
from hrms.hr.doctype.job_applicant.job_applicant import create_interview
from frappe.rate_limiter import rate_limit
from datetime import datetime
no_cache = 1


def get_context(context):
	applicant_id = frappe.form_dict.get("name")

	if not frappe.db.exists("Job Applicant", applicant_id):
		return {"status": "error", "message": "Job Applicant not found"}

	context.job_applicant = frappe.db.get_value("Job Applicant", applicant_id, ["applicant_name", "custom_interview_slot_booked"], as_dict=1)
	return context


@frappe.whitelist(allow_guest=True)
@rate_limit(limit=1, seconds=60)
def schedule_interview(applicant_id, interview_date, interview_slot):
	try:
		if not frappe.db.exists("Job Applicant", applicant_id):
			return {"status": "error", "message": "Job Applicant not found"}

		applicant_doc = frappe.get_doc("Job Applicant", applicant_id)
		interview_round = frappe.get_single("Recruitment Settings").interview_round
		if not interview_round:
			raise Exception(_("Interview Round is not set in Recruitment Settings"))

		interviewers = frappe.get_all("Assignment Rule User", filters={"parent": "Recruitment Settings"}, fields=["user"])
		start_time_str, end_time_str = interview_slot.split(" - ")
		from_time = datetime.strptime(start_time_str, "%H:%M:%S").time()
		to_time = datetime.strptime(end_time_str, "%H:%M:%S").time()
		interview = create_interview(applicant_doc, interview_round)
		interview.scheduled_on = interview_date
		interview.from_time = from_time
		interview.to_time = to_time
		if interviewers:
			for d in interviewers:
				interview.interview_details = []
				interview.append("interview_details", {
					"interviewer": d.user,
				})

		interview.save(ignore_permissions=True)

		applicant_doc.custom_interview_slot_booked = 1
		applicant_doc.save(ignore_permissions=True)
		return {"status": "success"}

	except Exception as e:
		frappe.log_error(f"Interview Scheduling Error: {str(e)}", "Schedule Interview")
		return {"status": "error", "message": "Error Contact Administrator"}


@frappe.whitelist(allow_guest=True)
def get_available_slots(applicant_id):
	slots_dict = {}

	interview_slots = frappe.get_all(
		"Interview Booking Slots",
		filters={"parent": applicant_id, "parenttype": "Job Applicant", "parentfield": "custom_available_slots"},
		fields=["date", "from_time", "to_time"],
		order_by="date asc, from_time asc"
	)

	for slot in interview_slots:
		date_str = slot.get("date").strftime("%-m/%-d/%Y")
		time_slot = f"{slot.get('from_time')} - {slot.get('to_time')}" 

		if date_str in slots_dict:
			slots_dict[date_str].append(time_slot)
		else:
			slots_dict[date_str] = [time_slot]

	formatted_slots = [{date: times} for date, times in slots_dict.items()]
	
	return formatted_slots
