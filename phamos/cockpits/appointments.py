# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Appointments of a cockpit: the Event Schedule rows ("Team Daily Schedule") of a parent document,
sent as Mailcow invites when the parent is saved (phamos.events.team_daily_schedule).

The General Management Cockpit uses its Department (#1949), the Team Cockpit the Team (#1979).
The callers check who may plan; these functions only read and change the parent's rows.
"""

import frappe
from frappe import _

from phamos.events import team_daily_schedule


EVENT_TABLE = "event_schedule"
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
REPEAT_OPTIONS = ("", "Daily", "Weekly", "Monthly", "Yearly")
# The row fields the cockpit may set. Sync fields (mailcow_*) stay with the sync.
APPOINTMENT_FIELDS = (
	"subject",
	"location",
	"description",
	"start",
	"end",
	"email_account",
	"repeat_this_event",
	"repeat_on",
	"repeat_till",
	*WEEKDAYS,
)


def _split_emails(value):
	return [part.strip() for part in (value or "").split(",") if part.strip()]


def _sync_error_line(text):
	"""One line of a stored sync error, short enough for the cockpit. A traceback's last line is
	the exception; any other message (e.g. "Mailcow PUT failed (503): <html>…") starts with the
	part that matters and may end in a server's HTML."""
	lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
	if not lines:
		return ""
	# "…" marks a traceback whose start was cut (team_daily_schedule._truncate_error keeps the end).
	is_traceback = lines[0].startswith(("Traceback (most recent call last)", "…"))
	return (lines[-1] if is_traceback else lines[0])[:300]


def _serialize_appointment(row):
	data = {field: row.get(field) for field in APPOINTMENT_FIELDS}
	data.update(
		{
			"name": row.name,
			"repeat_this_event": frappe.utils.cint(row.repeat_this_event),
			**{day: frappe.utils.cint(row.get(day)) for day in WEEKDAYS},
			"required_attendees": _split_emails(row.required_attendees),
			"optional_attendees": _split_emails(row.optional_attendees),
			"synced": bool(frappe.utils.cint(row.mailcow_synced)),
			"sync_error": _sync_error_line(row.mailcow_last_error),
			# a background job is sending the invite now; the dialog doesn't allow changes meanwhile
			"sending": team_daily_schedule.row_is_being_sent(row),
		}
	)
	return data


def _allowed_mailboxes():
	"""Email Accounts that can send invites: those with a Mailcow DAV password (as the Desk filter,
	team_daily_schedule.email_account_with_dav_password_query)."""
	return frappe.db.sql(
		"""
		SELECT DISTINCT ea.name, ea.email_id
		FROM `tabEmail Account` ea
		INNER JOIN `tabMailcow DAV Password` mdp ON mdp.user = ea.email_id
		ORDER BY ea.email_id ASC
		""",
		as_dict=True,
	)


def _save_events(parent_doc):
	"""Save the parent's Event Schedule for a user without write rights on it (#1949, #1979).

	The callers change only rows of event_schedule; ignore_permissions skips the parent's write
	check, while validation, the Mailcow sync (doc_events) and the version history still run.
	The Mailcow PUT/DELETE run in a background job after the commit (decision 10, #1949), so the
	call returns right away; the rows show "pending" until the job reports back.
	"""
	parent_doc.flags.ignore_permissions = True
	parent_doc.flags[team_daily_schedule.BACKGROUND_FLAG] = True
	parent_doc.save()


def _row(parent_doc, name):
	row = next((r for r in parent_doc.get(EVENT_TABLE) or [] if r.name == name), None)
	if not row:
		frappe.throw(_("Appointment {0} is not in the events of {1}.").format(name, parent_doc.name))
	return row


def _check_not_being_sent(row):
	"""Refuse to change or cancel an appointment whose invite a background job is still sending.
	A second job would send the same version and could mark the first one failed (#1949)."""
	if team_daily_schedule.row_is_being_sent(row):
		frappe.throw(_("The invite of this appointment is still being sent. Wait until it shows Sent or an error, then change it."))


def list_appointments(parent_doc):
	return [_serialize_appointment(row) for row in parent_doc.get(EVENT_TABLE) or []]


def appointment_options():
	"""What the appointment dialog offers: mailboxes (name, email_id) that can send invites, and
	departments: active Employees with a company email, grouped by department ({department, label,
	people: [{email, name, image}]}), people without a department last."""
	employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "company_email": ["is", "set"]},
		fields=["employee_name", "company_email", "department", "image"],
		order_by="employee_name asc",
	)
	groups = {}
	for employee in employees:
		groups.setdefault(employee.department or "", []).append(
			{"email": employee.company_email, "name": employee.employee_name, "image": employee.image}
		)
	labels = {
		row.name: row.department_name
		for row in frappe.get_all("Department", filters={"name": ["in", [d for d in groups if d]]}, fields=["name", "department_name"])
	}
	departments = [
		{"department": department, "label": labels.get(department, department) if department else _("No department"), "people": people}
		for department, people in sorted(groups.items(), key=lambda item: (not item[0], labels.get(item[0], item[0])))
	]
	return {"mailboxes": _allowed_mailboxes(), "departments": departments}


def save_appointment(parent_doc, appointment):
	"""Create or update an appointment of `parent_doc` and send its invite. `appointment`: `name` of
	the row to update (none: new), the fields in APPOINTMENT_FIELDS, and required_attendees /
	optional_attendees as lists of emails. Returns the saved appointment with its sync status."""
	data = frappe._dict(frappe.parse_json(appointment) or {})
	if not (data.subject or "").strip():
		frappe.throw(_("Subject is required"))
	if not data.start or not data.end:
		frappe.throw(_("Start and end are required"))
	if frappe.utils.get_datetime(data.end) < frappe.utils.get_datetime(data.start):
		frappe.throw(_("End cannot be before start"))
	if data.email_account not in {m.name for m in _allowed_mailboxes()}:
		frappe.throw(_("Pick a mailbox with a Mailcow calendar to send the invite."))
	if (data.repeat_on or "") not in REPEAT_OPTIONS:
		frappe.throw(_("Unknown repeat option {0}").format(data.repeat_on))
	if frappe.utils.cint(data.repeat_this_event):
		if not data.repeat_on:
			frappe.throw(_("Choose how often the appointment repeats"))
		if data.repeat_till and frappe.utils.getdate(data.repeat_till) < frappe.utils.getdate(data.start):
			frappe.throw(_("Repeat until cannot be before the start"))
	for field in ("required_attendees", "optional_attendees"):
		value = data.get(field) or []
		if not isinstance(value, list) or not all(isinstance(email, str) for email in value):
			frappe.throw(_("Attendees must be a list of email addresses"))

	values = {field: data.get(field) for field in APPOINTMENT_FIELDS if field in data}
	values["subject"] = data.subject.strip()
	values["repeat_this_event"] = frappe.utils.cint(data.repeat_this_event)
	for day in WEEKDAYS:
		values[day] = frappe.utils.cint(data.get(day))
	# Comma-separated, as the Events table stores them; validate_schedule_rows checks each address.
	values["required_attendees"] = ", ".join(data.required_attendees or [])
	values["optional_attendees"] = ", ".join(data.optional_attendees or [])

	if data.name:
		row = _row(parent_doc, data.name)
		_check_not_being_sent(row)
		row.update(values)
	else:
		row = parent_doc.append(EVENT_TABLE, values)
	_save_events(parent_doc)

	# The sync writes its status straight to the row in the database: read it back ("pending"
	# until the background job has sent the invite).
	saved = frappe.get_doc("Team Daily Schedule", row.name)
	return _serialize_appointment(saved)


def delete_appointment(parent_doc, name):
	"""Remove an appointment of `parent_doc`; the Mailcow sync cancels its invite."""
	_check_not_being_sent(_row(parent_doc, name))
	parent_doc.set(EVENT_TABLE, [row for row in parent_doc.get(EVENT_TABLE) if row.name != name])
	_save_events(parent_doc)
	return {"deleted": name}
