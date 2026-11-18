# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""General Management cockpit API — department-scoped Issues, Tasks and Checklists (#1946).

Unlike the department cockpits, only the role `phamos General Management` (and System Manager)
gets in: reading Issues or Tasks is not enough. Every whitelisted function checks this first.
"""

import functools

import frappe
from frappe import _

from phamos.api import department_cockpit as dc
from phamos.cockpits.settings import COCKPIT_SETTINGS, COCKPITS, cockpit_window
from phamos.events import team_daily_schedule
from phamos.setup.general_management import GENERAL_MANAGEMENT_ROLE

ACCESS_ROLES = ("System Manager", GENERAL_MANAGEMENT_ROLE)

CONFIG = dc.CockpitConfig(
	label="General Management",
	department_field="general_management_department",
	project_field="general_management_timesheet_project",
	roles=ACCESS_ROLES,
	settings_method_name="get_general_management_settings",
)


def check_app_permission():
	"""True for Administrator and the ACCESS_ROLES; everyone else stays out (Apps screen, page, API).

	Deliberately not dc.check_app_permission, which also lets in anyone who can read Issue or Task.
	"""
	user = frappe.session.user
	if user in (None, "Guest"):
		return False
	if user == "Administrator":
		return True
	return bool(set(frappe.get_roles(user)) & set(ACCESS_ROLES))


def _require_access(fn):
	"""Refuse a whitelisted call unless check_app_permission() passes.

	functools.wraps keeps the signature, which frappe uses to pick the request arguments.
	"""

	@functools.wraps(fn)
	def wrapper(*args, **kwargs):
		if not check_app_permission():
			frappe.throw(
				_("You do not have permission to access the General Management Cockpit"),
				frappe.PermissionError,
			)
		return fn(*args, **kwargs)

	# Marker for the tests; functools.wraps carries it up through frappe.whitelist's own wrapper.
	wrapper.requires_general_management = True
	return wrapper


@frappe.whitelist()
@_require_access
def get_general_management_settings():
	"""Return the General Management cockpit configuration for the frontend.

	Requires read permission on Issue (checked in department_cockpit.get_settings).

	Returns:
		dict: general_management_department, general_management_timesheet_project,
		general_management_timesheet_project_name (the project's title) and
		general_management_project_count (projects linked to the department).
	"""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
@_require_access
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the General Management timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
@_require_access
def get_inbox(view="assigned", include_closed=0):
	"""Return General Management-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issues(include_closed=0):
	"""Return all General Management department Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
@_require_access
def get_issue(name):
	"""Return Issue detail if it belongs to General Management scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_form_options():
	"""Form options scoped to General Management department."""
	return dc.get_form_options(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create a General Management-scoped Issue."""
	return dc.create_issue(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_status(name, status):
	"""Update Issue status within General Management scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_assignees(name, users=None):
	"""Replace Issue assignees within General Management scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist()
@_require_access
def get_issue_chat(name):
	"""Return the Raven chat state of an Issue in General Management scope."""
	return dc.get_issue_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_issue_chat(name):
	"""Start or join the Raven chat of an Issue in General Management scope."""
	return dc.ensure_issue_chat(CONFIG, name)


@frappe.whitelist()
@_require_access
def get_issue_chat_states(names):
	"""Return the chat state per Issue for list views."""
	return dc.get_issue_chat_states(names)


@frappe.whitelist()
@_require_access
def get_task_chat(name):
	"""Return the Raven chat state of a Task in General Management scope."""
	return dc.get_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def ensure_task_chat(name):
	"""Start or join the Raven chat of a Task in General Management scope."""
	return dc.ensure_task_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_issue(
	name, subject=None, description=None, priority=None, issue_type=None, project=None, modified=None
):
	"""Update whitelisted Issue fields within General Management scope."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if issue_type is not None:
		fields["issue_type"] = issue_type
	if project is not None:
		fields["project"] = project
	if modified is not None:
		fields["modified"] = modified
	return dc.update_issue(CONFIG, name, **fields)


@frappe.whitelist()
@_require_access
def get_tasks(include_completed=0):
	"""Return Tasks for the General Management department."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklists(include_completed=0):
	"""Return Checklists linked to General Management Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
@_require_access
def get_checklist_dashboard():
	"""Return General Management Checklist dashboard metrics and chart data."""
	return dc.get_checklist_dashboard(CONFIG)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_checklist(
	document,
	reference_record,
	name=None,
	items=None,
	checklist_owner=None,
	checklist_template=None,
):
	"""Create a Checklist linked to a General Management Issue or Task."""
	return dc.create_checklist(
		CONFIG,
		document,
		reference_record,
		name=name,
		items=items,
		checklist_owner=checklist_owner,
		checklist_template=checklist_template,
	)


@frappe.whitelist()
@_require_access
@frappe.validate_and_sanitize_search_inputs
def checklist_reference_query(doctype, txt, searchfield, start, page_len, filters):
	"""Search General Management-scoped Issue/Task parents for Checklist creation.

	The access check sits outside frappe's sanitiser: that one finds `searchfield` among the
	positional arguments by the names of the function it wraps, so it must wrap this one (#1956).
	"""
	return dc.checklist_reference_query(CONFIG, doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
@_require_access
def get_task(name):
	"""Return Task detail for the General Management SPA."""
	return dc.get_task(CONFIG, name)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	return dc.update_task_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	return dc.update_task_dates(CONFIG, name, exp_start_date=exp_start_date, exp_end_date=exp_end_date)


@frappe.whitelist(methods=["POST"])
@_require_access
def update_task(
	name,
	subject=None,
	description=None,
	priority=None,
	status=None,
	exp_start_date=None,
	exp_end_date=None,
	progress=None,
	project=None,
	custom_task_owner=None,
	modified=None,
):
	"""Update whitelisted Task fields within General Management scope."""
	fields = {}
	if subject is not None:
		fields["subject"] = subject
	if description is not None:
		fields["description"] = description
	if priority is not None:
		fields["priority"] = priority
	if status is not None:
		fields["status"] = status
	if exp_start_date is not None:
		fields["exp_start_date"] = exp_start_date
	if exp_end_date is not None:
		fields["exp_end_date"] = exp_end_date
	if progress is not None:
		fields["progress"] = progress
	if project is not None:
		fields["project"] = project
	if custom_task_owner is not None:
		fields["custom_task_owner"] = custom_task_owner
	if modified is not None:
		fields["modified"] = modified
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
@_require_access
def set_task_assignees(name, users=None):
	"""Replace Task assignees within General Management scope."""
	return dc.set_task_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
	expected_time=None,
	custom_task_owner=None,
	task_type=None,
):
	"""Create a Task in the General Management department."""
	return dc.create_task(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		project=project,
		department=department,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		expected_time=expected_time,
		custom_task_owner=custom_task_owner,
		task_type=task_type,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def create_task_from_issue(
	issue_name,
	exp_start_date,
	exp_end_date,
	assignees=None,
	subject=None,
	description=None,
	priority=None,
	project=None,
	depends_on=None,
):
	"""Convert an Issue into a Task (General Management cockpit hand-off)."""
	return dc.create_task_from_issue(
		CONFIG,
		issue_name,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
		assignees=assignees,
		subject=subject,
		description=description,
		priority=priority,
		project=project,
		depends_on=depends_on,
	)


@frappe.whitelist(methods=["POST"])
@_require_access
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)


# --- Company view: "All departments" on the Tasks Gantt (#1948) ---------------------------------

# Cap per department, like department_cockpit.get_tasks.
COMPANY_TASKS_PER_DEPARTMENT = 500
OWN_PREFIX = "general_management"


def _company_cockpits():
	"""The cockpits with a department set in Cockpit Settings, General Management first.

	Returns:
		list[dict]: department, label (the cockpit's name), color (Cockpit Settings, else the
		cockpit's default), route and own (True for General Management). The others follow in the
		order of their tabs in Cockpit Settings. The Personal Cockpit has no department.
	"""
	field_order = [field.fieldname for field in frappe.get_meta(COCKPIT_SETTINGS).fields]
	cockpits = []
	for route, (prefix, default_color) in COCKPITS.items():
		department_field = f"{prefix}_department"
		if department_field not in field_order:
			continue
		department = frappe.db.get_single_value(COCKPIT_SETTINGS, department_field)
		if not department:
			continue
		cockpits.append(
			{
				"department": department,
				"label": prefix.replace("_", " ").title(),
				"color": cockpit_window(route)["color"] or default_color,
				"route": route,
				"own": prefix == OWN_PREFIX,
				"_position": field_order.index(department_field),
			}
		)
	cockpits.sort(key=lambda c: (not c["own"], c["_position"]))
	for cockpit in cockpits:
		del cockpit["_position"]
	return cockpits


@frappe.whitelist()
@_require_access
def get_company_tasks(include_completed=0):
	"""Top-level Tasks of every cockpit department, one group per department (#1948).

	Subtasks (with a Parent Task) stay in the department cockpits. Completed and cancelled Tasks
	only with include_completed, as in department_cockpit.get_tasks.

	Returns:
		list[dict]: the groups of _company_cockpits(), each with its `tasks` (get_tasks rows).
	"""
	frappe.has_permission("Task", "read", throw=True)
	include_completed = frappe.utils.cint(include_completed)
	groups = []
	for cockpit in _company_cockpits():
		filters = [["department", "=", cockpit["department"]], ["parent_task", "is", "not set"]]
		if not include_completed:
			filters.append(["status", "not in", ["Cancelled", "Template", "Completed"]])
		rows = frappe.get_list(
			"Task",
			filters=filters,
			fields=dc.TASK_LIST_FIELDS,
			order_by="exp_start_date asc, modified desc",
			limit_page_length=COMPANY_TASKS_PER_DEPARTMENT,
		)
		groups.append({**cockpit, "tasks": [dc._serialize_task_row(row) for row in rows]})
	return groups


@frappe.whitelist()
@_require_access
def get_company_task(name):
	"""Read-only detail of a Task of a cockpit department, for the company view (#1948).

	Returns:
		dict: the department_cockpit task detail plus `cockpit` (label, color, route, own) of the
		Task's department. Throws for a Task outside the cockpit departments.
	"""
	doc = frappe.get_doc("Task", name)
	doc.check_permission("read")
	cockpit = next((c for c in _company_cockpits() if c["department"] == doc.department), None)
	if not cockpit:
		frappe.throw(_("This task is not in a department with a cockpit."), frappe.PermissionError)
	return {**dc._serialize_task_detail(doc), "cockpit": cockpit}


# --- Company appointments (#1949) ---------------------------------------------------------------
# Company-wide appointments are the rows of the General Management Department's Event Schedule
# ("Team Daily Schedule", phamos/setup/event_schedule.py); saving the Department sends them as
# Mailcow invites (phamos.events.team_daily_schedule), whose source link then points to it.

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


def _appointments_department():
	"""The General Management Department from Cockpit Settings, or throw."""
	department = frappe.db.get_single_value(COCKPIT_SETTINGS, CONFIG.department_field)
	if not department:
		frappe.throw(_("Configure {0} Department in Cockpit Settings.").format(CONFIG.label))
	return department


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


def _save_department_events(department_doc):
	"""Save the Department's Event Schedule for a manager without Department rights (#1949).

	The callers change only rows of event_schedule; ignore_permissions skips the Department write
	check, while validation, the Mailcow sync (doc_events) and the version history still run.
	The Mailcow PUT/DELETE run in a background job after the commit (decision 10, #1949), so the
	call returns right away; the rows show "pending" until the job reports back.
	"""
	department_doc.flags.ignore_permissions = True
	department_doc.flags[team_daily_schedule.BACKGROUND_FLAG] = True
	department_doc.save()


def _department_row(department_doc, name):
	row = next((r for r in department_doc.get(EVENT_TABLE) or [] if r.name == name), None)
	if not row:
		frappe.throw(_("Appointment {0} is not in the events of {1}.").format(name, department_doc.name))
	return row


def _check_not_being_sent(row):
	"""Refuse to change or cancel an appointment whose invite a background job is still sending.
	A second job would send the same version and could mark the first one failed (#1949)."""
	if team_daily_schedule.row_is_being_sent(row):
		frappe.throw(_("The invite of this appointment is still being sent. Wait until it shows Sent or an error, then change it."))


@frappe.whitelist()
@_require_access
def get_company_appointments():
	"""Company-wide appointments: the Event Schedule rows of the General Management Department.

	Returns:
		dict: department, department_label and appointments (rows with attendee lists and the
		Mailcow sync status).
	"""
	department_doc = frappe.get_doc("Department", _appointments_department())
	return {
		"department": department_doc.name,
		"department_label": department_doc.department_name,
		"appointments": [_serialize_appointment(row) for row in department_doc.get(EVENT_TABLE) or []],
	}


@frappe.whitelist()
@_require_access
def get_appointment_options():
	"""What the appointment dialog offers.

	Returns:
		dict: mailboxes (name, email_id) that can send invites, and departments: active Employees
		with a company email, grouped by department ({department, label, people: [{email,
		name, image}]}), people without a department last.
	"""
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


@frappe.whitelist(methods=["POST"])
@_require_access
def save_appointment(appointment):
	"""Create or update a company appointment (an Event Schedule row of the General Management
	Department) and send its invite.

	Args:
		appointment (dict | str): `name` of the row to update (none: new), the fields in
			APPOINTMENT_FIELDS, and required_attendees / optional_attendees as lists of emails.

	Returns:
		dict: the saved appointment, with its sync status after the save.
	"""
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

	department_doc = frappe.get_doc("Department", _appointments_department())
	if data.name:
		row = _department_row(department_doc, data.name)
		_check_not_being_sent(row)
		row.update(values)
	else:
		row = department_doc.append(EVENT_TABLE, values)
	_save_department_events(department_doc)

	# The sync writes its status straight to the row in the database: read it back ("pending"
	# until the background job has sent the invite).
	saved = frappe.get_doc("Team Daily Schedule", row.name)
	return _serialize_appointment(saved)


@frappe.whitelist(methods=["POST"])
@_require_access
def delete_appointment(name):
	"""Remove a company appointment; the Mailcow sync cancels its invite."""
	department_doc = frappe.get_doc("Department", _appointments_department())
	_check_not_being_sent(_department_row(department_doc, name))
	department_doc.set(EVENT_TABLE, [row for row in department_doc.get(EVENT_TABLE) if row.name != name])
	_save_department_events(department_doc)
	return {"deleted": name}
