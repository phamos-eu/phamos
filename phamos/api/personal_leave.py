# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""My leave in the Personal Cockpit (phamos/phamos#1714).

The employee hands in leave with status Open and never submits it; the leave approver from
the Employee record decides in Desk (#1714, Q1 and Q4). Every function works on the session
user's own Employee and takes no employee argument:

- reads use `frappe.get_all` filtered to that Employee, like `personal_contracts`; the filter
  is the access check
- applying and editing go through the Leave Application document API, so HRMS validation
  (balance, overlap, block days, backdating) and its messages apply unchanged
- withdrawing deletes the application with `ignore_permissions`, because the Employee role
  has no delete right, but only for the user's own leave that is still Open and unsubmitted
  (#1714, Q8); Phase 2's `on_trash` hook then removes the calendar event
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from phamos.cockpits.workdays import _employee

DOCTYPE = "Leave Application"
COVER_FIELD = "custom_cover_employee"
STATUSES = ("Open", "Approved", "Rejected", "Cancelled")
LIST_FIELDS = [
	"name",
	"leave_type",
	"from_date",
	"to_date",
	"half_day",
	"half_day_date",
	"total_leave_days",
	"status",
	"docstatus",
	"leave_approver",
	"leave_approver_name",
	"description",
	"posting_date",
	"modified",
]
EDITABLE_FIELDS = ("leave_type", "from_date", "to_date", "half_day", "half_day_date", "description")


def _my_employee() -> str | None:
	return _employee(frappe.session.user)


def _has_cover_field() -> bool:
	return frappe.get_meta(DOCTYPE).has_field(COVER_FIELD)


def _employee_names(names) -> dict:
	names = [n for n in set(names) if n]
	if not names:
		return {}
	rows = frappe.get_all("Employee", filters={"name": ["in", names]}, fields=["name", "employee_name"])
	return {r.name: r.employee_name for r in rows}


def _calendar_states(leave_names: list[str]) -> dict:
	"""Calendar state per Leave Application, from the Events Phase 2 keeps for them."""
	if not leave_names:
		return {}
	rows = frappe.get_all(
		"Event",
		filters={"reference_doctype": DOCTYPE, "reference_docname": ["in", leave_names]},
		fields=["name", "reference_docname", "custom_mailcow_synched", "custom_mailcow_sync_error"],
		order_by="creation asc",
	)
	states = {}
	for row in rows:
		if row.reference_docname in states:
			continue
		if row.custom_mailcow_sync_error:
			state = "error"
		elif row.custom_mailcow_synched:
			state = "synced"
		else:
			state = "pending"
		states[row.reference_docname] = {
			"event": row.name,
			"state": state,
			"error": row.custom_mailcow_sync_error or "",
		}
	return states


def _serialize(row, cover_names: dict, calendar: dict) -> dict:
	editable = row.docstatus == 0 and row.status == "Open"
	cover = row.get(COVER_FIELD)
	return {
		"name": row.name,
		"leave_type": row.leave_type,
		"from_date": str(row.from_date) if row.from_date else None,
		"to_date": str(row.to_date) if row.to_date else None,
		"half_day": cint(row.half_day),
		"half_day_date": str(row.half_day_date) if row.half_day_date else None,
		"total_leave_days": flt(row.total_leave_days),
		"status": row.status,
		"docstatus": row.docstatus,
		"submitted": row.docstatus == 1,
		"leave_approver": row.leave_approver,
		"leave_approver_name": row.leave_approver_name or row.leave_approver,
		"cover_employee": cover,
		"cover_employee_name": cover_names.get(cover) if cover else None,
		"description": row.description or "",
		"posting_date": str(row.posting_date) if row.posting_date else None,
		"modified": str(row.modified),
		"editable": editable,
		"calendar": calendar.get(row.name) or {"event": None, "state": "none", "error": ""},
	}


def _rows(employee: str, filters: dict | None = None) -> list:
	fields = list(LIST_FIELDS)
	if _has_cover_field():
		fields.append(COVER_FIELD)
	# ignore permissions on purpose: the filter on the user's own Employee is the access check
	return frappe.get_all(
		DOCTYPE,
		filters={"employee": employee, **(filters or {})},
		fields=fields,
		order_by="from_date desc, creation desc",
	)


def _serialize_rows(rows) -> list[dict]:
	cover_names = _employee_names(r.get(COVER_FIELD) for r in rows)
	calendar = _calendar_states([r.name for r in rows])
	return [_serialize(r, cover_names, calendar) for r in rows]


def get_my_leave(status: str | None = None) -> dict:
	"""All my Leave Applications, newest first, optionally of one status (#1714, Q7)."""
	employee = _my_employee()
	if not employee:
		return {"has_employee": False, "leave": []}
	filters = {}
	if status:
		if status not in STATUSES:
			frappe.throw(_("Unknown status {0}.").format(status))
		filters["status"] = status
	return {
		"has_employee": True,
		"employee": employee,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
		"leave": _serialize_rows(_rows(employee, filters)),
	}


def get_my_leave_entry(name: str) -> dict:
	employee = _my_employee()
	rows = _rows(employee, {"name": name}) if employee else []
	if not rows:
		frappe.throw(_("This leave application is not yours."), frappe.PermissionError)
	return _serialize_rows(rows)[0]


def _leave_details(employee: str, date) -> dict:
	from hrms.hr.doctype.leave_application.leave_application import get_leave_details

	return get_leave_details(employee, getdate(date or nowdate()))


def get_my_leave_balance(date: str | None = None) -> dict:
	"""Remaining days per allocated leave type on `date` (default today), from HRMS."""
	employee = _my_employee()
	if not employee:
		return {"has_employee": False, "balance": [], "without_pay": []}
	details = _leave_details(employee, date)
	balance = [
		{
			"leave_type": leave_type,
			"allocated": flt(values.get("total_leaves")),
			"taken": flt(values.get("leaves_taken")),
			"pending": flt(values.get("leaves_pending_approval")),
			"expired": flt(values.get("expired_leaves")),
			"remaining": flt(values.get("remaining_leaves")),
		}
		for leave_type, values in sorted((details.get("leave_allocation") or {}).items())
	]
	return {"has_employee": True, "balance": balance, "without_pay": details.get("lwps") or []}


def get_leave_form_options(from_date: str | None = None) -> dict:
	"""Leave types as HRMS offers them to me (#1714, Q5), my approver, colleagues for cover."""
	employee = _my_employee()
	if not employee:
		return {"has_employee": False, "leave_types": [], "leave_approver": None, "cover_employees": []}
	details = _leave_details(employee, from_date)
	allocated = details.get("leave_allocation") or {}
	leave_types = [
		{"value": leave_type, "remaining": flt(values.get("remaining_leaves")), "without_pay": False}
		for leave_type, values in sorted(allocated.items())
	]
	leave_types += [
		{"value": leave_type, "remaining": None, "without_pay": True}
		for leave_type in sorted(details.get("lwps") or [])
		if leave_type not in allocated
	]
	approver = frappe.db.get_value("Employee", employee, "leave_approver") or details.get("leave_approver")
	cover_employees = frappe.get_all(
		"Employee",
		filters={"status": "Active", "name": ["!=", employee]},
		fields=["name", "employee_name"],
		order_by="employee_name asc",
	)
	return {
		"has_employee": True,
		"leave_types": leave_types,
		"leave_approver": approver,
		"leave_approver_name": frappe.db.get_value("User", approver, "full_name") if approver else None,
		"cover_employees": [{"value": r.name, "label": r.employee_name or r.name} for r in cover_employees],
		"has_cover_field": _has_cover_field(),
	}


def _values(leave_type, from_date, to_date, half_day, half_day_date, description, cover_employee) -> dict:
	half_day = cint(half_day)
	values = {
		"leave_type": leave_type,
		"from_date": getdate(from_date) if from_date else None,
		"to_date": getdate(to_date) if to_date else None,
		"half_day": half_day,
		"half_day_date": getdate(half_day_date) if (half_day and half_day_date) else None,
		"description": (description or "").strip() or None,
	}
	if _has_cover_field():
		values[COVER_FIELD] = cover_employee or None
	if not values["leave_type"] or not values["from_date"] or not values["to_date"]:
		frappe.throw(_("Leave type, from and to date are required."))
	return values


def apply_leave(
	leave_type,
	from_date,
	to_date,
	half_day=0,
	half_day_date=None,
	description=None,
	cover_employee=None,
) -> dict:
	"""Hand in leave as Open for my leave approver (#1714, Q1)."""
	employee = _my_employee()
	if not employee:
		frappe.throw(_("Your user has no active Employee record."))
	values = _values(leave_type, from_date, to_date, half_day, half_day_date, description, cover_employee)
	approver = frappe.db.get_value("Employee", employee, "leave_approver")
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"employee": employee,
			"leave_approver": approver,
			"posting_date": nowdate(),
			**values,
		}
	)
	# status keeps its default Open; it is permlevel 1 and belongs to the approver
	doc.insert()
	return get_my_leave_entry(doc.name)


def _own_open_leave(name: str):
	employee = _my_employee()
	if not employee or not frappe.db.exists(DOCTYPE, name):
		frappe.throw(_("This leave application is not yours."), frappe.PermissionError)
	doc = frappe.get_doc(DOCTYPE, name)
	if doc.employee != employee:
		frappe.throw(_("This leave application is not yours."), frappe.PermissionError)
	if doc.docstatus != 0 or doc.status != "Open":
		frappe.throw(
			_("Only open leave can be changed. Ask HR to change approved, rejected or cancelled leave."),
			frappe.PermissionError,
		)
	return doc


def update_leave(
	name,
	leave_type,
	from_date,
	to_date,
	half_day=0,
	half_day_date=None,
	description=None,
	cover_employee=None,
	modified=None,
) -> dict:
	"""Edit my own leave while it is still Open (#1714, Q8)."""
	doc = _own_open_leave(name)
	if modified and str(doc.modified) != str(modified):
		frappe.throw(_("Someone changed this leave application in the meantime. Reload and try again."))
	doc.update(_values(leave_type, from_date, to_date, half_day, half_day_date, description, cover_employee))
	doc.save()
	return get_my_leave_entry(doc.name)


def withdraw_leave(name) -> dict:
	"""Delete my own leave while it is still Open (#1714, Q8)."""
	doc = _own_open_leave(name)
	frappe.delete_doc(DOCTYPE, doc.name, ignore_permissions=True)
	return {"name": name, "withdrawn": True}
