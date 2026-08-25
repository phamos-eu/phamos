# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Project Management SPA API — department-scoped Issues and Tasks."""

import json
import re
from collections import OrderedDict
from datetime import date

import frappe
from frappe import _
from frappe.utils import cint, flt, get_fullname, getdate, today

from phamos.api import department_cockpit as dc

CONFIG = dc.CockpitConfig(
	label="Project Management",
	department_field="pm_department",
	project_field="pm_timesheet_project",
	roles=("System Manager", "Projects Manager", "Projects User"),
	settings_method_name="get_pm_settings",
)

ACTIVE_IMPLEMENTATION_STATUSES = ("Open", "Reactivated", "Hold", "Escalated")

IMPLEMENTATION_QUEUE_FIELDS = [
	"name",
	"customer",
	"account_manager",
	"maturity_level",
	"forecast",
	"trend",
	"status",
	"department",
	"team",
	"status_statement",
	"modified",
]


def check_app_permission():
	"""Show Project Management Cockpit on the Apps screen for eligible users."""
	return dc.check_app_permission(CONFIG)


def _user_label(user):
	if not user:
		return ""
	return get_fullname(user) or user


@frappe.whitelist()
def get_pm_settings():
	"""Return Project Management Cockpit configuration for the frontend."""
	return dc.get_settings(CONFIG)


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the Project Management timesheet project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return Project Management-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to Project Management scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to Project Management department."""
	return dc.get_form_options(CONFIG)


@frappe.whitelist(methods=["POST"])
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create a Project Management-scoped Issue."""
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
def update_status(name, status):
	"""Update Issue status within Project Management scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def set_assignees(name, users=None):
	"""Replace Issue assignees within Project Management scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return Tasks for the Project Management department."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the Project Management Cockpit."""
	return dc.get_task(CONFIG, name)


@frappe.whitelist(methods=["POST"])
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	return dc.update_task_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	return dc.update_task_dates(CONFIG, name, exp_start_date=exp_start_date, exp_end_date=exp_end_date)


@frappe.whitelist(methods=["POST"])
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
):
	"""Create a Task in the Project Management department."""
	return dc.create_task(
		CONFIG,
		subject,
		description=description,
		priority=priority,
		project=project,
		department=department,
		exp_start_date=exp_start_date,
		exp_end_date=exp_end_date,
	)


@frappe.whitelist(methods=["POST"])
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)


@frappe.whitelist()
def get_chat_settings():
	"""SPA soft-dependency flags for Raven chat."""
	return dc.get_chat_settings()


def _require_implementation_read():
	frappe.has_permission("Implementation", "read", throw=True)


def _require_implementation_write():
	frappe.has_permission("Implementation", "write", throw=True)


def _implementation_field_options(fieldname):
	meta = frappe.get_meta("Implementation")
	field = meta.get_field(fieldname)
	if not field or not field.options:
		return []
	return [opt for opt in field.options.split("\n") if opt]


def _active_implementation_filters():
	return [["status", "in", list(ACTIVE_IMPLEMENTATION_STATUSES)]]


def _get_reviewed_today_names(names=None):
	"""Return set of Implementation names with a status_updates row dated today."""
	if names is not None and not names:
		return set()

	filters = {"parenttype": "Implementation", "parentfield": "status_updates", "date": today()}
	if names is not None:
		filters["parent"] = ["in", names]

	rows = frappe.get_all("Status Information", filters=filters, pluck="parent")
	return set(rows or [])


def _next_calendar_months(count=3):
	"""Return list of YYYY-MM strings for current month and following months."""
	base = getdate(today())
	current = date(base.year, base.month, 1)
	months = []
	for offset in range(count):
		year = current.year + ((current.month - 1 + offset) // 12)
		month = ((current.month - 1 + offset) % 12) + 1
		months.append(f"{year:04d}-{month:02d}")
	return months


def _maturity_sort_key(maturity_level):
	if not maturity_level:
		return 99
	match = re.match(r"^(\d+)", str(maturity_level).strip())
	if match:
		return cint(match.group(1))
	return 99


def _maturity_short_label(maturity_level, maturity_sort=None):
	sort = maturity_sort if maturity_sort is not None else _maturity_sort_key(maturity_level)
	if sort == 99:
		return "Unassigned"
	return f"Level {sort}"


def _maturity_group_title(maturity_level, maturity_sort=None):
	sort = maturity_sort if maturity_sort is not None else _maturity_sort_key(maturity_level)
	if sort == 99:
		return "Unassigned maturity"
	if maturity_level:
		return maturity_level
	return f"Level {sort}"


def _require_todo_read():
	frappe.has_permission("ToDo", "read", throw=True)


def _require_todo_write():
	frappe.has_permission("ToDo", "create", throw=True)


def _get_todo_users():
	users = frappe.get_all(
		"User",
		filters={"enabled": 1, "user_type": "System User"},
		fields=["name", "full_name"],
		order_by="full_name asc",
		limit_page_length=500,
	)
	return [{"name": u.name, "full_name": u.full_name or u.name} for u in users]


def _serialize_todo_row(row):
	allocated_to = row.get("allocated_to")
	return {
		"name": row.get("name"),
		"description": row.get("description") or "",
		"date": row.get("date"),
		"allocated_to": allocated_to,
		"assignee_name": _user_label(allocated_to),
		"status": row.get("status"),
		"priority": row.get("priority"),
		"desk_url": f"/app/todo/{row.get('name')}",
	}


def _fetch_todos_by_implementation(names):
	if not names:
		return {}

	rows = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Implementation",
			"reference_name": ["in", names],
			"status": "Open",
		},
		fields=["name", "description", "date", "allocated_to", "status", "priority", "reference_name"],
		order_by="date asc, modified desc",
		limit_page_length=2000,
	)

	grouped = {name: [] for name in names}
	for row in rows:
		ref = row.get("reference_name")
		if ref in grouped:
			grouped[ref].append(_serialize_todo_row(row))
	return grouped


def _serialize_queue_row(row, reviewed_today, todos=None):
	account_manager = row.get("account_manager")
	maturity_level = row.get("maturity_level")
	maturity_sort = _maturity_sort_key(maturity_level)
	return {
		"name": row.get("name"),
		"customer": row.get("customer"),
		"account_manager": account_manager,
		"owner_name": _user_label(account_manager),
		"maturity_level": maturity_level,
		"maturity_sort": maturity_sort,
		"maturity_label": _maturity_short_label(maturity_level, maturity_sort),
		"maturity_group_title": _maturity_group_title(maturity_level, maturity_sort),
		"forecast": row.get("forecast"),
		"trend": row.get("trend"),
		"status": row.get("status"),
		"department": row.get("department"),
		"team": row.get("team"),
		"reviewed_today": reviewed_today,
		"todos": todos or [],
		"desk_url": f"/app/implementation/{row.get('name')}",
	}


def _sort_weekly_monitoring_rows(rows):
	return sorted(
		rows,
		key=lambda row: (row.get("maturity_sort", 99), (row.get("name") or "").lower()),
	)


def _group_weekly_monitoring_rows(rows):
	groups = OrderedDict()
	for row in rows:
		key = row.get("maturity_sort", 99)
		if key not in groups:
			groups[key] = {
				"maturity_sort": key,
				"maturity_label": row.get("maturity_label") or _maturity_short_label(None, key),
				"maturity_group_title": row.get("maturity_group_title")
				or _maturity_group_title(None, key),
				"items": [],
			}
		groups[key]["items"].append(row)

	result = []
	for group in groups.values():
		reviewed = sum(1 for item in group["items"] if item.get("reviewed_today"))
		group["reviewed_count"] = reviewed
		group["total_count"] = len(group["items"])
		result.append(group)
	return result


def _get_weekly_monitoring_rows():
	_require_implementation_read()
	rows = frappe.get_list(
		"Implementation",
		filters=_active_implementation_filters(),
		fields=IMPLEMENTATION_QUEUE_FIELDS,
		order_by="name asc",
		limit_page_length=500,
	)
	names = [row.name for row in rows]
	reviewed = _get_reviewed_today_names(names)
	todos_by_name = _fetch_todos_by_implementation(names)

	serialized = [
		_serialize_queue_row(
			row,
			row.name in reviewed,
			todos_by_name.get(row.name, []),
		)
		for row in rows
	]
	return _sort_weekly_monitoring_rows(serialized)


def _build_weekly_monitoring_queue():
	rows = _get_weekly_monitoring_rows()
	reviewed_today_count = sum(1 for row in rows if row.get("reviewed_today"))
	return {
		"groups": _group_weekly_monitoring_rows(rows),
		"total_count": len(rows),
		"reviewed_today_count": reviewed_today_count,
	}


def _get_previous_status_row(implementation_name):
	rows = frappe.get_all(
		"Status Information",
		filters={
			"parent": implementation_name,
			"parenttype": "Implementation",
			"parentfield": "status_updates",
			"date": ["<", today()],
		},
		fields=["date", "maturity_level", "forecast", "trend", "status_statement", "status"],
		order_by="date desc",
		limit=1,
	)
	return rows[0] if rows else None


def _predictions_for_next_months(doc, month_keys=None):
	month_keys = month_keys or _next_calendar_months(3)
	by_month = {}
	for row in doc.resource_planning_prediction or []:
		key = (row.month_and_year or "").strip()
		if key in month_keys and key not in by_month:
			by_month[key] = flt(row.prediction)

	return [{"month_and_year": key, "prediction": by_month.get(key, 0)} for key in month_keys]


def _upsert_predictions(doc, predictions):
	if isinstance(predictions, str):
		predictions = json.loads(predictions or "[]")

	predictions_by_month = {}
	for row in predictions or []:
		key = (row.get("month_and_year") or "").strip()
		if key:
			predictions_by_month[key] = cint(row.get("prediction") or 0)

	for month_key, prediction in predictions_by_month.items():
		found = False
		for row in doc.resource_planning_prediction or []:
			if (row.month_and_year or "").strip() == month_key:
				row.prediction = prediction
				row.date = today()
				found = True
				break
		if not found:
			doc.append(
				"resource_planning_prediction",
				{"month_and_year": month_key, "prediction": prediction, "date": today()},
			)


def _next_pending_implementation_name(current_name=None):
	rows = _get_weekly_monitoring_rows()
	pending = [row for row in rows if not row.get("reviewed_today")]

	if not current_name:
		return pending[0]["name"] if pending else None

	seen_current = False
	for row in rows:
		if row.get("name") == current_name:
			seen_current = True
			continue
		if seen_current and not row.get("reviewed_today"):
			return row.get("name")

	for row in pending:
		if row.get("name") != current_name:
			return row.get("name")
	return None


def _build_weekly_monitoring_detail(doc):
	from phamos.phamos.doctype.implementation.implementation import get_financial_history

	financial = get_financial_history(doc.name, doc.customer) or {}
	reviewed_today = doc.name in _get_reviewed_today_names([doc.name])

	return {
		"name": doc.name,
		"customer": doc.customer,
		"department": doc.department,
		"team": doc.team,
		"status": doc.status,
		"account_manager": doc.account_manager,
		"owner_name": _user_label(doc.account_manager),
		"maturity_level": doc.maturity_level,
		"maturity_sort": _maturity_sort_key(doc.maturity_level),
		"maturity_label": _maturity_short_label(doc.maturity_level),
		"maturity_group_title": _maturity_group_title(doc.maturity_level),
		"reviewed_today": reviewed_today,
		"desk_url": f"/app/implementation/{doc.name}",
		"financial": {
			"sales_order_total_hrs": int(flt(financial.get("sales_order_qty"))),
			"delivered_total_hrs": flt(financial.get("dn_qty")),
			"total_hrs_timesheet": flt(financial.get("timesheet_hrs")),
			"remaining_hrs": flt(financial.get("remaining_hrs")),
		},
		"stats": {
			"total_time_last_3_months": flt(doc.total_time_last_3_months),
			"predicted_time_next_3_months": flt(doc.predicted_time_next_3_months),
		},
		"previous_status": _get_previous_status_row(doc.name),
		"values": {
			"maturity_level": doc.maturity_level,
			"forecast": doc.forecast,
			"trend": doc.trend,
			"status_statement": doc.status_statement or "",
		},
		"predictions": _predictions_for_next_months(doc),
		"todos": _fetch_todos_by_implementation([doc.name]).get(doc.name, []),
		"users": _get_todo_users(),
		"options": {
			"maturity_level": _implementation_field_options("maturity_level"),
			"forecast": _implementation_field_options("forecast"),
			"trend": _implementation_field_options("trend"),
		},
	}


@frappe.whitelist()
def get_implementations_hub_summary():
	"""Summary counts for the Implementations hub."""
	_require_implementation_read()
	queue = _build_weekly_monitoring_queue()
	return {
		"active_count": queue["total_count"],
		"reviewed_today_count": queue["reviewed_today_count"],
	}


@frappe.whitelist()
def get_weekly_monitoring_queue():
	"""Active implementations for the weekly monitoring meeting."""
	return _build_weekly_monitoring_queue()


@frappe.whitelist()
def get_weekly_monitoring_todo_users():
	"""Active users for weekly monitoring todo assignee picker."""
	_require_todo_read()
	return _get_todo_users()


@frappe.whitelist()
def get_implementation_todos(implementation):
	"""Open ToDos linked to an Implementation."""
	_require_implementation_read()
	_require_todo_read()
	frappe.get_doc("Implementation", implementation).check_permission("read")
	return _fetch_todos_by_implementation([implementation]).get(implementation, [])


@frappe.whitelist(methods=["POST"])
def create_implementation_todo(implementation, description, date=None, allocated_to=None):
	"""Create a ToDo linked to an Implementation."""
	_require_implementation_write()
	_require_todo_write()

	description = (description or "").strip()
	if not description:
		frappe.throw(_("Description is required"))

	frappe.get_doc("Implementation", implementation).check_permission("read")

	doc = frappe.get_doc(
		{
			"doctype": "ToDo",
			"description": description,
			"reference_type": "Implementation",
			"reference_name": implementation,
			"status": "Open",
			"assigned_by": frappe.session.user,
		}
	)
	if date:
		doc.date = date
	if allocated_to:
		doc.allocated_to = allocated_to
	doc.insert()

	return _serialize_todo_row(doc.as_dict())


@frappe.whitelist(methods=["POST"])
def close_implementation_todo(name):
	"""Close an open ToDo linked to an Implementation."""
	_require_todo_write()
	doc = frappe.get_doc("ToDo", name)
	if doc.reference_type != "Implementation":
		frappe.throw(_("Only Implementation to-dos can be closed here"))
	doc.check_permission("write")
	if doc.status == "Closed":
		return {"name": doc.name, "status": "Closed"}
	doc.status = "Closed"
	doc.save()
	return {"name": doc.name, "status": "Closed"}


@frappe.whitelist()
def get_weekly_monitoring_detail(name):
	"""Full detail payload for one implementation review step."""
	_require_implementation_read()
	doc = frappe.get_doc("Implementation", name)
	doc.check_permission("read")
	if doc.status not in ACTIVE_IMPLEMENTATION_STATUSES:
		frappe.throw(_("This implementation is not in the weekly monitoring queue."))
	return _build_weekly_monitoring_detail(doc)


@frappe.whitelist(methods=["POST"])
def save_weekly_monitoring(
	name,
	maturity_level=None,
	forecast=None,
	trend=None,
	status_statement=None,
	predictions=None,
):
	"""Save weekly monitoring updates for one implementation."""
	_require_implementation_write()
	doc = frappe.get_doc("Implementation", name)
	doc.check_permission("write")
	if doc.status not in ACTIVE_IMPLEMENTATION_STATUSES:
		frappe.throw(_("This implementation is not in the weekly monitoring queue."))

	if maturity_level is not None:
		doc.maturity_level = maturity_level
	if forecast is not None:
		doc.forecast = forecast
	if trend is not None:
		doc.trend = trend
	if status_statement is not None:
		doc.status_statement = status_statement

	if predictions is not None:
		_upsert_predictions(doc, predictions)

	doc.save()

	updated = _build_weekly_monitoring_detail(doc)
	updated["next_name"] = _next_pending_implementation_name(name)
	return updated


# Re-export Raven chat APIs for a stable SPA method prefix
from phamos.api.issue_raven import (  # noqa: E402, F401
	ensure_document_channel,
	get_chat_messages,
	get_document_chat,
	get_raven_users_for_invite,
	get_thread,
	invite_to_document_channel,
	open_or_create_thread,
	send_chat_message,
)
