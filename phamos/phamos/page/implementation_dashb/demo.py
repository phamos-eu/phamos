"""Demo data for the hours chart on the Implementation Dashboard (phamos/phamos#2199). Developer sites only.

    bench --site dev.localhost execute phamos.phamos.page.implementation_dashb.demo.seed

Months are relative to today, so the data stays useful when you run it again later. Each run
deletes the demo Timesheets and creates them again. All records start with "DEMO".
`bench execute` commits at the end, so the script does not commit itself.

Cases:
- DEMO Impl A: hours every month from -8 to the current month, predictions from now to +6.
- DEMO Impl B: one past month with no hours (a real 0) and one month with no prediction (a gap).
- DEMO Impl C: work ended 3 months ago (0 after that, not cut early).
- DEMO Internal: an internal project, shown as "Internal Projects".
Every month with hours has billable hours: a month with only non-billable hours gets no chart row.
"""

import frappe
from frappe import _
from frappe.utils import add_months, get_first_day, getdate, today

CUSTOMER = "DEMO Chart Customer"
ACTIVITY = "DEMO Chart Work"

# name: (months with hours, months with a prediction)
IMPLEMENTATIONS = {
	"DEMO Impl A": (range(-8, 1), range(0, 7)),
	"DEMO Impl B": ([m for m in range(-6, 1) if m != -3], [m for m in range(0, 6) if m != 2]),
	"DEMO Impl C": (range(-8, -2), []),
}
INTERNAL = ("DEMO Internal", range(-5, 1))


def seed():
	if not frappe.conf.developer_mode:
		frappe.throw(_("The Implementation Dashboard demo seed only runs on developer sites (developer_mode = 1)."))
	frappe.flags.mute_emails = True
	company = frappe.defaults.get_global_default("company")
	_ensure_customer()
	_ensure_activity_type()

	for slot, (name, (hour_months, prediction_months)) in enumerate(IMPLEMENTATIONS.items()):
		impl = _ensure_implementation(name)
		project = _ensure_project(f"{name} Project", company, implementation=impl.name)
		_replace_timesheets(project, company, hour_months, slot)
		_rebuild_implementation(impl.name, prediction_months)

	internal_name, internal_months = INTERNAL
	internal = _ensure_project(internal_name, company, internal=True)
	_replace_timesheets(internal, company, internal_months, slot=len(IMPLEMENTATIONS))
	print("Demo data ready. Open /app/implementation-dashb")


def _ensure_implementation(name):
	if frappe.db.exists("Implementation", name):
		return frappe.get_doc("Implementation", name)
	doc = frappe.get_doc({"doctype": "Implementation", "customer": CUSTOMER, "status": "Open"})
	doc.name = name
	return doc.insert(set_name=name)


def _ensure_project(project_name, company, implementation=None, internal=False):
	name = frappe.db.get_value("Project", {"project_name": project_name})
	if name:
		return name
	return frappe.get_doc({
		"doctype": "Project",
		"project_name": project_name,
		"company": company,
		"status": "Open",
		"project_owner": "Administrator",
		"custom_implementation": implementation,
		"custom_is_internal_project": 1 if internal else 0,
	}).insert().name


def _replace_timesheets(project, company, month_offsets, slot):
	for name in frappe.get_all("Timesheet", {"parent_project": project}, pluck="name"):
		doc = frappe.get_doc("Timesheet", name)
		if doc.docstatus == 1:
			doc.cancel()
		frappe.delete_doc("Timesheet", name, force=True)
	for offset in month_offsets:
		_timesheet(project, company, offset, slot)


def _timesheet(project, company, offset, slot):
	# One Timesheet per month: add_resource_planning groups by the Timesheet's start date.
	# All logs are on the 1st (never in the future); each project gets its own 6-hour slot,
	# because ERPNext rejects overlapping logs of the same user.
	day = get_first_day(add_months(today(), offset))
	start = 6 * slot
	billable, non_billable = _hours_for(offset)
	doc = frappe.get_doc({
		"doctype": "Timesheet",
		"company": company,
		"parent_project": project,
		"time_logs": [
			_log(project, f"{day} {start:02d}:00:00", billable, is_billable=True),
			_log(project, f"{day} {start + billable:02d}:00:00", non_billable, is_billable=False),
		],
	})
	doc.insert()
	doc.submit()


def _log(project, from_time, hours, is_billable):
	return {
		"activity_type": ACTIVITY,
		"project": project,
		"from_time": from_time,
		"hours": hours,
		"is_billable": 1 if is_billable else 0,
		"billing_hours": hours if is_billable else 0,
	}


def _hours_for(offset):
	# Varied but repeatable values, so the stacked areas are easy to tell apart.
	return 2 + (offset % 3), 1 + (offset % 2)


def _rebuild_implementation(name, prediction_months):
	# Saving rebuilds the "Resource planning" rows from the Timesheets.
	doc = frappe.get_doc("Implementation", name)
	doc.resource_planning_prediction = []
	for offset in prediction_months:
		month = getdate(add_months(today(), offset)).strftime("%Y-%m")
		doc.append("resource_planning_prediction", {"month_and_year": month, "prediction": 6 + offset, "date": today()})
	doc.save()


def _ensure_customer():
	if frappe.db.exists("Customer", CUSTOMER):
		return
	frappe.get_doc({
		"doctype": "Customer",
		"customer_name": CUSTOMER,
		"customer_group": _first_leaf("Customer Group"),
		"territory": _first_leaf("Territory"),
	}).insert()


def _ensure_activity_type():
	if not frappe.db.exists("Activity Type", ACTIVITY):
		frappe.get_doc({"doctype": "Activity Type", "activity_type": ACTIVITY}).insert()


def _first_leaf(doctype):
	return frappe.get_all(doctype, {"is_group": 0}, pluck="name", limit=1)[0]
