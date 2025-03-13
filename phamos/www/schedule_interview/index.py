from frappe import _
import frappe
from hrms.hr.doctype.job_applicant.job_applicant import create_interview
from frappe.core.doctype.communication.email import _make as make_communication
from email.utils import formataddr
from frappe.rate_limiter import rate_limit
from datetime import datetime, timedelta
from ics import Calendar, Event, Attendee
import pytz
import hashlib

no_cache = 1


def get_context(context):
	applicant_id = frappe.form_dict.get("name")

	if not frappe.db.exists("Job Applicant", applicant_id):
		return {"status": "error", "message": "Job Applicant not found"}

	context.job_applicant = frappe.db.get_value("Job Applicant", applicant_id, ["applicant_name", "designation", "custom_interview_slot_booked"], as_dict=1)
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

		cc = []
		if interviewers:
			for d in interviewers:
				interview.interview_details = []
				interview.append("interview_details", {
					"interviewer": d.user,
				})
				cc.append(d.user)

		interview.save(ignore_permissions=True)

		applicant_doc.custom_interview_slot_booked = 1
		applicant_doc.save(ignore_permissions=True)
		recipients = [applicant_doc.email_id]
		send_interview_schedule_email(applicant_doc, interview.scheduled_on, interview_slot, recipients, cc=cc)
		return {"status": "success"}

	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"Interview Scheduling Error: {str(e)} \n {frappe.get_traceback()}", "Schedule Interview")
		return {"status": "error", "message": "Contact Administrator"}


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


def send_interview_schedule_email(applicant_doc, interview_date, interview_slot, recipients, cc=[]):
	recruitement_settings = frappe.get_doc("Recruitment Settings")
	if applicant_doc.designation:
		job_title = "<b>{0}</b> position".format(applicant_doc.designation)
	else:
		job_title = "job"

	sender = None
	if recruitement_settings.sender and recruitement_settings.sender_email:
		sender = formataddr((recruitement_settings.sender, recruitement_settings.sender_email))
	else:
		raise Exception(_("Sender Email is not set in Recruitment Settings"))
	
	if not recruitement_settings.interview_confirmation:
		raise Exception(_("Interview Confirmation Email Template is not set in Recruitment Settings"))

	email_template = frappe.get_doc("Email Template", recruitement_settings.interview_confirmation)
	subject = email_template.subject

	key = f"For-{applicant_doc.designation}-Candidate-{applicant_doc.applicant_name}"
	hashed_value = hashlib.sha256(key.encode()).hexdigest()
	short_hash = str(int(hashed_value, 16))[:7] 
	interview_link = f"https://meet.jit.si/JobInterviewPhamos-{short_hash}"
	ics_filename, ics_data = create_interview_ics(applicant_doc, interview_date, interview_slot, interview_link, cc=cc)
	attachments = [{"fname": ics_filename, "fcontent": ics_data}]

	message = frappe.render_template(email_template.response_html, {
		"applicant_name": applicant_doc.get("applicant_name", "Candidate"),
		"job_title": job_title,
		"interview_date": interview_date,
		"interview_slot": interview_slot,
		"interview_link": interview_link
	})

	communication = make_communication(
		doctype=applicant_doc.doctype,
		name=applicant_doc.name,
		content=message,
		subject=subject,
		sender=sender,
		recipients=recipients,
		communication_medium="Email",
		send_email=False,
		attachments=attachments,
		cc=cc,
		communication_type="Automated Message",
	).get("name")

	frappe.sendmail(
		recipients=recipients,
		subject=subject,
		sender=sender,
		cc=cc,
		message=message,
		reference_doctype=applicant_doc.doctype,
		reference_name=applicant_doc.name,
		attachments=attachments,
		expose_recipients="header",
		communication=communication,
	)


def create_interview_ics(applicant_doc, interview_date, interview_slot, meeting_link, timezone_str="Europe/Berlin", cc=[]):
	start_time_str, end_time_str = interview_slot.split(" - ")
	start_datetime = datetime.strptime(f"{interview_date} {start_time_str}", "%Y-%m-%d %H:%M:%S")
	end_datetime = datetime.strptime(f"{interview_date} {end_time_str}", "%Y-%m-%d %H:%M:%S")
	timezone = pytz.timezone(timezone_str)
	
	cal = Calendar()
	event = Event()
	event.name = f"Interview: {applicant_doc.applicant_name}"
	event.begin = start_datetime
	event.end = end_datetime
	event.description = f"Interview for {applicant_doc.applicant_name}\nMeeting Link: {meeting_link}"
	event.location = meeting_link if meeting_link else "Office"
	event.duration = timedelta(hours=1)
	event.alarm = timedelta(minutes=-30)
	event.tz = timezone

	attendees = [Attendee(applicant_doc.email_id, applicant_doc.applicant_name)]
	for interviewer in cc:
		interviewer_name = frappe.db.get_value("User", interviewer, "full_name")
		attendees.append(Attendee(interviewer, interviewer_name))
	event.attendees = attendees

	cal.events.add(event)

	ics_filename = f"{applicant_doc.applicant_name}_interview.ics".replace(" ", "_")

	return ics_filename, cal.serialize()