# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting SPA API — department-scoped Issues/Tasks and Accounting Receipts."""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.load import get_assignments
from frappe.utils import get_fullname

from phamos.api.i_own_my_work import (
	ALLOWED_STATUSES,
	LIST_FIELDS,
	_parse_assignees,
	_parse_list,
	_serialize_issue_row,
	_status_filters,
)
from phamos.api.i_own_my_work import get_issue as _get_issue
from phamos.api.i_own_my_work import set_assignees as _set_assignees
from phamos.api.i_own_my_work import update_status as _update_status

TASK_LIST_FIELDS = [
	"name",
	"subject",
	"description",
	"status",
	"priority",
	"project",
	"department",
	"exp_start_date",
	"exp_end_date",
	"progress",
	"color",
	"depends_on_tasks",
	"modified",
	"_assign",
]

TASK_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed", "Cancelled", "Template")
TASK_KANBAN_STATUSES = ("Open", "Working", "Pending Review", "Overdue", "Completed")
TASK_ACTIVE_STATUSES = ("Open", "Working", "Pending Review", "Overdue")


def check_app_permission():
	"""Show Accounting SPA on the Apps screen for eligible users."""
	if frappe.session.user in (None, "Guest"):
		return False
	if frappe.session.user == "Administrator":
		return True

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type == "Website User":
		return False

	roles = set(frappe.get_roles())
	if roles & {"System Manager", "Accounts Manager", "Accounts User"}:
		return True

	return (
		frappe.has_permission("Issue", ptype="read")
		or frappe.has_permission("Task", ptype="read")
		or frappe.has_permission("Accounting Receipt", ptype="read")
	)


def _user_label(user):
	if not user:
		return ""
	return get_fullname(user) or user


def _get_accounting_settings_doc():
	return frappe.get_cached_doc("phamos Settings")


def _get_accounting_department():
	return frappe.db.get_single_value("phamos Settings", "accounting_department")


def _get_accounting_standard_project():
	return frappe.db.get_single_value("phamos Settings", "accounting_standard_project")


def _get_accounting_project_names(department=None):
	"""Projects linked to the Accounting department."""
	department = department or _get_accounting_department()
	if not department:
		return []
	return frappe.get_all(
		"Project",
		filters={"department": department},
		pluck="name",
		limit_page_length=500,
	)


def _accounting_issue_or_filters(department=None):
	"""Match issues scoped to Accounting via project department or Issue.custom_department."""
	department = department or _get_accounting_department()
	if not department:
		return []

	or_filters = []
	project_names = _get_accounting_project_names(department)
	if project_names:
		or_filters.append(["project", "in", project_names])
	if frappe.get_meta("Issue").has_field("custom_department"):
		or_filters.append(["custom_department", "=", department])
	return or_filters


def _issue_in_accounting_scope(doc):
	"""True when issue belongs to the configured Accounting department."""
	department = _get_accounting_department()
	if not department:
		return False

	if getattr(doc, "custom_department", None) == department:
		return True

	if doc.project:
		project_department = frappe.db.get_value("Project", doc.project, "department")
		if project_department == department:
			return True

	return False


def _ensure_issue_in_accounting_scope(doc):
	if not _issue_in_accounting_scope(doc):
		frappe.throw(_("This issue is not in the Accounting department scope."))


def _require_accounting_department():
	department = _get_accounting_department()
	if not department:
		frappe.throw(
			_("Accounting Department is not configured in phamos Settings."),
			title=_("Configuration required"),
		)
	return department


def _validate_accounting_project(project):
	if not project:
		frappe.throw(_("Project is required for Accounting issues."))
	department = _require_accounting_department()
	project_department = frappe.db.get_value("Project", project, "department")
	if project_department != department:
		frappe.throw(
			_("Project {0} is not linked to Accounting department {1}.").format(project, department)
		)


@frappe.whitelist()
def get_accounting_settings():
	"""Return Accounting SPA configuration for the frontend."""
	if not (
		frappe.has_permission("Issue", "read")
		or frappe.has_permission("Task", "read")
		or frappe.has_permission("Accounting Receipt", "read")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	from phamos.api.issue_raven import get_chat_feature_flags

	department = _get_accounting_department()
	standard_project = _get_accounting_standard_project()
	project_names = _get_accounting_project_names(department)

	project_label = None
	if standard_project:
		project_label = frappe.db.get_value("Project", standard_project, "project_name") or standard_project

	return {
		"accounting_department": department,
		"accounting_standard_project": standard_project,
		"accounting_standard_project_name": project_label,
		"accounting_project_count": len(project_names),
		"chat": get_chat_feature_flags(),
	}


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the Accounting standard project (start-modal dropdown)."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_accounting_department()
	project = project or _get_accounting_standard_project()
	if not project:
		return []

	_validate_accounting_project(project)

	rows = frappe.get_list(
		"Task",
		filters={
			"department": department,
			"project": project,
			"status": ("not in", ["Cancelled", "Template", "Completed"]),
		},
		fields=["name", "subject"],
		order_by="modified desc",
		limit_page_length=200,
	)
	return rows


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return Accounting-scoped Issues for the current user: assigned | created."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_accounting_department()

	view = (view or "assigned").lower()
	include_closed = frappe.utils.cint(include_closed)
	user = frappe.session.user
	filters = _status_filters(include_closed)
	or_filters = _accounting_issue_or_filters()
	if not or_filters:
		return []

	if view == "created":
		filters.append(["owner", "=", user])
		rows = frappe.get_list(
			"Issue",
			filters=filters,
			or_filters=or_filters,
			fields=LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=200,
		)
	else:
		todos = frappe.get_all(
			"ToDo",
			filters={
				"reference_type": "Issue",
				"allocated_to": user,
				"status": ("not in", ("Cancelled", "Closed")),
			},
			fields=["reference_name"],
			limit_page_length=500,
		)
		names = list({t.reference_name for t in todos if t.reference_name})
		if not names:
			return []
		filters.append(["name", "in", names])
		rows = frappe.get_list(
			"Issue",
			filters=filters,
			or_filters=or_filters,
			fields=LIST_FIELDS,
			order_by="modified desc",
			limit_page_length=200,
		)

	return [_serialize_issue_row(r) for r in rows]


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to Accounting scope."""
	frappe.has_permission("Issue", "read", throw=True)
	_require_accounting_department()

	doc = frappe.get_doc("Issue", name)
	doc.check_permission("read")
	_ensure_issue_in_accounting_scope(doc)

	return _get_issue(name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to Accounting department."""
	frappe.has_permission("Issue", "read", throw=True)
	department = _require_accounting_department()

	from phamos.api.i_own_my_work import get_form_options as _base_options

	options = _base_options()
	project_names = set(_get_accounting_project_names(department))
	standard_project = _get_accounting_standard_project()
	if standard_project:
		project_names.add(standard_project)
	options["departments"] = [department]
	if project_names:
		options["projects"] = [p for p in options.get("projects", []) if p["name"] in project_names]
	options["accounting_department"] = department
	options["accounting_standard_project"] = _get_accounting_standard_project()
	options["chat"] = get_chat_settings()
	return options


@frappe.whitelist()
def create_issue(
	subject,
	description=None,
	priority=None,
	issue_type=None,
	assign_to=None,
	project=None,
	department=None,
):
	"""Create an Accounting-scoped Issue."""
	frappe.has_permission("Issue", "create", throw=True)
	accounting_department = _require_accounting_department()

	if not project:
		project = _get_accounting_standard_project()
	if not department:
		department = accounting_department

	if department != accounting_department and project:
		_validate_accounting_project(project)

	from phamos.api.i_own_my_work import create_issue as _create

	return _create(
		subject=subject,
		description=description,
		priority=priority,
		issue_type=issue_type,
		assign_to=assign_to,
		project=project,
		department=department,
	)


@frappe.whitelist()
def update_status(name, status):
	"""Update Issue status within Accounting scope."""
	get_issue(name)
	return _update_status(name, status)


@frappe.whitelist()
def set_assignees(name, users=None):
	"""Replace Issue assignees within Accounting scope."""
	get_issue(name)
	return _set_assignees(name, users)


def _serialize_task_row(row):
	assignees = _parse_assignees(row.get("_assign"))
	return {
		"name": row.get("name"),
		"subject": row.get("subject"),
		"description": row.get("description") or "",
		"status": row.get("status"),
		"priority": row.get("priority"),
		"project": row.get("project"),
		"department": row.get("department"),
		"exp_start_date": row.get("exp_start_date"),
		"exp_end_date": row.get("exp_end_date"),
		"progress": row.get("progress") or 0,
		"color": row.get("color"),
		"depends_on_tasks": row.get("depends_on_tasks") or "",
		"modified": row.get("modified"),
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
	}


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return Tasks for the Accounting department."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_accounting_department()
	include_completed = frappe.utils.cint(include_completed)

	filters = [["department", "=", department]]
	if not include_completed:
		filters.append(["status", "not in", ["Cancelled", "Template", "Completed"]])

	rows = frappe.get_list(
		"Task",
		filters=filters,
		fields=TASK_LIST_FIELDS,
		order_by="exp_start_date asc, modified desc",
		limit_page_length=500,
	)
	return [_serialize_task_row(r) for r in rows]


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the Accounting SPA."""
	frappe.has_permission("Task", "read", throw=True)
	department = _require_accounting_department()

	doc = frappe.get_doc("Task", name)
	doc.check_permission("read")
	if doc.department != department:
		frappe.throw(_("This task is not in the Accounting department."))

	assignees = [a.get("owner") for a in get_assignments("Task", doc.name)]
	return {
		"name": doc.name,
		"subject": doc.subject,
		"description": doc.description or "",
		"status": doc.status,
		"priority": doc.priority,
		"project": doc.project,
		"department": doc.department,
		"exp_start_date": doc.exp_start_date,
		"exp_end_date": doc.exp_end_date,
		"progress": doc.progress or 0,
		"color": doc.color,
		"depends_on_tasks": doc.depends_on_tasks or "",
		"owner": doc.owner,
		"owner_name": _user_label(doc.owner),
		"modified": doc.modified,
		"assignees": assignees,
		"assignee_names": [_user_label(u) for u in assignees],
		"desk_url": f"/app/task/{doc.name}",
	}


@frappe.whitelist()
def update_task_status(name, status):
	"""Update Task status (Kanban drag)."""
	frappe.has_permission("Task", "write", throw=True)
	status = (status or "").strip()
	if status not in TASK_KANBAN_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))

	get_task(name)
	doc = frappe.get_doc("Task", name)
	doc.status = status
	doc.save()
	return get_task(name)


@frappe.whitelist()
def update_task_dates(name, exp_start_date=None, exp_end_date=None):
	"""Update Task expected dates (Gantt drag)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(name)

	doc = frappe.get_doc("Task", name)
	if exp_start_date:
		doc.exp_start_date = exp_start_date
	if exp_end_date:
		doc.exp_end_date = exp_end_date
	doc.save()
	return get_task(name)


@frappe.whitelist()
def create_task(
	subject,
	description=None,
	priority=None,
	project=None,
	department=None,
	exp_start_date=None,
	exp_end_date=None,
):
	"""Create a Task in the Accounting department."""
	frappe.has_permission("Task", "create", throw=True)
	accounting_department = _require_accounting_department()

	subject = (subject or "").strip()
	if not subject:
		frappe.throw(_("Subject is required"))

	if not department:
		department = accounting_department
	if department != accounting_department:
		frappe.throw(_("Task department must match Accounting department in phamos Settings."))

	if not project:
		project = _get_accounting_standard_project()
	if project:
		_validate_accounting_project(project)

	doc = frappe.get_doc(
		{
			"doctype": "Task",
			"subject": subject,
			"status": "Open",
			"department": department,
			"project": project,
		}
	)
	if description:
		doc.description = description
	if priority:
		doc.priority = priority
	if exp_start_date:
		doc.exp_start_date = exp_start_date
	if exp_end_date:
		doc.exp_end_date = exp_end_date
	doc.insert()
	return get_task(doc.name)


@frappe.whitelist()
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	frappe.has_permission("Task", "write", throw=True)
	get_task(name)
	get_task(depends_on)

	if name == depends_on:
		frappe.throw(_("A task cannot depend on itself."))

	doc = frappe.get_doc("Task", name)
	existing = {row.task for row in doc.depends_on if row.task}
	if depends_on in existing:
		return get_task(name)

	doc.append("depends_on", {"task": depends_on})
	doc.save()
	return get_task(name)


@frappe.whitelist()
def get_chat_settings():
	"""SPA soft-dependency flags for Raven chat."""
	from phamos.api.issue_raven import get_chat_feature_flags

	return get_chat_feature_flags()


RECEIPT_KANBAN_STATUSES = (
	"Inbox",
	"Needs Decision",
	"Approved to Pay",
	"Do Not Pay",
	"Sent to DATEV",
	"Paid",
)

RECEIPT_LIST_FIELDS = [
	"name",
	"title",
	"posting_date",
	"sum",
	"currency",
	"supplier_reference",
	"status",
	"is_paid",
	"sent_to_datev",
	"supplier",
	"supplier_name",
	"receipt_type",
	"modified",
]


def _derive_receipt_status(row):
	"""Map flags + status field to a kanban column."""
	status = (row.get("status") or "").strip()
	if status in RECEIPT_KANBAN_STATUSES:
		return status
	if row.get("is_paid"):
		return "Paid"
	if row.get("sent_to_datev"):
		return "Sent to DATEV"
	return "Inbox"


def _serialize_receipt_row(row):
	status = _derive_receipt_status(row)
	attachment = row.get("attachment") or ""
	has_pdf = bool(attachment and str(attachment).lower().endswith(".pdf"))
	return {
		"name": row.get("name"),
		"title": row.get("title"),
		"posting_date": row.get("posting_date"),
		"sum": row.get("sum"),
		"currency": row.get("currency"),
		"supplier_reference": row.get("supplier_reference"),
		"status": status,
		"is_paid": 1 if row.get("is_paid") else 0,
		"sent_to_datev": 1 if row.get("sent_to_datev") else 0,
		"supplier": row.get("supplier"),
		"supplier_name": row.get("supplier_name"),
		"receipt_type": row.get("receipt_type"),
		"modified": row.get("modified"),
		"attachment": attachment,
		"has_pdf": has_pdf,
		"desk_url": f"/app/accounting-receipt/{row.get('name')}",
	}


def _apply_receipt_status_flags(doc, status):
	"""Keep is_paid / sent_to_datev in sync with kanban status."""
	doc.status = status
	if status == "Paid":
		doc.is_paid = 1
	elif status == "Sent to DATEV":
		doc.sent_to_datev = 1
		doc.is_paid = 0
	else:
		# Leaving terminal columns: clear payment flag so status can stick
		doc.is_paid = 0
		# Keep sent_to_datev as audit trail once emailed; do not clear


@frappe.whitelist()
def get_receipts():
	"""Return Accounting Receipts for the Receipts kanban."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)

	rows = frappe.get_list(
		"Accounting Receipt",
		fields=RECEIPT_LIST_FIELDS,
		order_by="posting_date desc, modified desc",
		limit_page_length=500,
	)
	return [_serialize_receipt_row(r) for r in rows]


@frappe.whitelist()
def get_receipt(name):
	"""Return a single Accounting Receipt for the SPA detail panel."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")
	return _serialize_receipt_row(
		{
			"name": doc.name,
			"title": doc.title,
			"posting_date": doc.posting_date,
			"sum": doc.sum,
			"currency": doc.currency,
			"supplier_reference": doc.supplier_reference,
			"status": doc.status,
			"is_paid": doc.is_paid,
			"sent_to_datev": doc.sent_to_datev,
			"supplier": doc.supplier,
			"supplier_name": doc.supplier_name,
			"receipt_type": doc.receipt_type,
			"modified": doc.modified,
			"attachment": doc.attachment or "",
		}
	)


@frappe.whitelist()
def update_receipt_status(name, status):
	"""Update Accounting Receipt status from kanban drag."""
	frappe.has_permission("Accounting Receipt", "write", throw=True)
	status = (status or "").strip()
	if status not in RECEIPT_KANBAN_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	_apply_receipt_status_flags(doc, status)
	doc.save()
	return get_receipt(name)


EXTRACT_CACHE_TTL = 3600


def _receipt_extract_cache_key(name):
	return f"accounting_receipt_extract:{name}"


def _set_receipt_extract_status(name, payload):
	frappe.cache.set_value(_receipt_extract_cache_key(name), payload, expires_in_sec=EXTRACT_CACHE_TTL)


def _get_receipt_extract_status(name):
	return frappe.cache.get_value(_receipt_extract_cache_key(name)) or {"status": "idle"}


def _run_receipt_pdf_extract_job(accounting_receipt_name):
	from phamos.phamos.doctype.accounting_receipt.mistral_pdf import extract_from_pdf_and_update_ar

	try:
		result = extract_from_pdf_and_update_ar(accounting_receipt_name)
		if result.get("ok"):
			_set_receipt_extract_status(
				accounting_receipt_name,
				{
					"status": "done",
					"updated": result.get("updated") or [],
					"skipped": result.get("skipped") or [],
				},
			)
		else:
			_set_receipt_extract_status(
				accounting_receipt_name,
				{
					"status": "failed",
					"reason": result.get("reason"),
					"message": result.get("message"),
				},
			)
	except Exception as e:
		_set_receipt_extract_status(
			accounting_receipt_name,
			{"status": "failed", "reason": "error", "message": str(e)},
		)


@frappe.whitelist()
def enqueue_receipt_pdf_extract(name):
	"""Queue background PDF extraction + auto-apply for a receipt opened in the SPA."""
	frappe.has_permission("Accounting Receipt", "write", throw=True)
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")

	attachment = (doc.attachment or "").strip()
	if not attachment or not attachment.lower().endswith(".pdf"):
		return {"queued": False, "reason": "no_attachment"}

	current = _get_receipt_extract_status(name)
	if current.get("status") == "running":
		return {"queued": False, "reason": "already_running", "status": current}

	_set_receipt_extract_status(
		name,
		{"status": "running", "started_at": frappe.utils.now()},
	)
	frappe.enqueue(
		_run_receipt_pdf_extract_job,
		queue="default",
		timeout=300,
		accounting_receipt_name=name,
		enqueue_after_commit=True,
	)
	return {"queued": True, "status": {"status": "running"}}


@frappe.whitelist()
def get_receipt_extract_status(name):
	"""Return background PDF extraction status for SPA polling."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	frappe.get_doc("Accounting Receipt", name).check_permission("read")
	return _get_receipt_extract_status(name)


@frappe.whitelist()
def get_receipt_review_fields(name):
	"""Return review-dialog field payload from current receipt values (no re-OCR)."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("read")

	from phamos.phamos.doctype.accounting_receipt.mistral_pdf import build_review_fields_from_doc

	fields, extracted = build_review_fields_from_doc(doc)
	return {"ok": True, "fields": fields, "extracted": extracted}


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
