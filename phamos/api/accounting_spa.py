# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting SPA API — department-scoped Issues/Tasks and Accounting Receipts."""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.desk.form.load import get_assignments
from frappe.utils import flt, get_fullname

from phamos.api import department_cockpit as dc
from phamos.api.i_own_my_work import _parse_assignees, _parse_list

CONFIG = dc.CockpitConfig(
	label="Accounting",
	department_field="accounting_department",
	project_field="accounting_standard_project",
	roles=("System Manager", "Accounts Manager", "Accounts User"),
	settings_method_name="get_accounting_settings",
)

MIS_DOCTYPE = "Monthly Implementation Summary"

MIS_LIST_FIELDS = [
	"name",
	"implementation",
	"status",
	"year",
	"month",
	"total_hours",
	"billable_hours",
	"modified",
	"_assign",
]


def check_app_permission():
	"""Show Accounting SPA on the Apps screen for eligible users."""
	return dc.check_app_permission(
		CONFIG,
		extra_doctypes=("Accounting Receipt", MIS_DOCTYPE),
	)


def _accounting_settings_permission():
	if not (
		frappe.has_permission("Issue", "read")
		or frappe.has_permission("Task", "read")
		or frappe.has_permission("Accounting Receipt", "read")
		or frappe.has_permission(MIS_DOCTYPE, "read")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _can_read_mis():
	return bool(frappe.has_permission(MIS_DOCTYPE, "read"))


@frappe.whitelist()
def get_accounting_settings():
	"""Return Accounting SPA configuration for the frontend."""
	settings = dc.get_settings(CONFIG, read_permission=_accounting_settings_permission)
	settings["can_read_monthly_implementation_summary"] = 1 if _can_read_mis() else 0
	return settings


def _user_info_map(users):
	"""Map user name → {full_name, user_image} in one query."""
	names = list({u for u in (users or []) if u})
	if not names:
		return {}
	rows = frappe.get_all(
		"User",
		filters={"name": ("in", names)},
		fields=["name", "full_name", "user_image"],
	)
	return {
		r.name: {
			"full_name": r.full_name or r.name,
			"user_image": r.user_image,
		}
		for r in rows
	}


def _mis_delta(total_hours, billable_hours):
	"""Return non-billable hours and ratio of total (None when total is zero)."""
	total = flt(total_hours)
	billable = flt(billable_hours)
	delta_hours = total - billable
	delta_ratio = None if total == 0 else delta_hours / total
	return delta_hours, delta_ratio


def _serialize_mis_row(row, assignees=None, user_info=None):
	if assignees is None:
		assignees = _parse_assignees(row.get("_assign"))
	info = user_info if user_info is not None else _user_info_map(assignees)
	total_hours = flt(row.get("total_hours"))
	billable_hours = flt(row.get("billable_hours"))
	delta_hours, delta_ratio = _mis_delta(total_hours, billable_hours)
	name = row.get("name")
	return {
		"name": name,
		"implementation": row.get("implementation"),
		"status": row.get("status"),
		"year": row.get("year"),
		"month": row.get("month"),
		"total_hours": total_hours,
		"billable_hours": billable_hours,
		"delta_hours": delta_hours,
		"delta_ratio": delta_ratio,
		"modified": row.get("modified"),
		"assignees": assignees,
		"assignee_names": [
			(info.get(u) or {}).get("full_name") or get_fullname(u) or u for u in assignees
		],
		"assignee_images": [(info.get(u) or {}).get("user_image") for u in assignees],
		"desk_url": f"/app/monthly-implementation-summary/{name}",
	}


def _require_mis_read():
	frappe.has_permission(MIS_DOCTYPE, "read", throw=True)


@frappe.whitelist()
def get_monthly_implementation_summaries():
	"""Return Monthly Implementation Summary rows the current user may read."""
	_require_mis_read()

	rows = frappe.get_list(
		MIS_DOCTYPE,
		fields=MIS_LIST_FIELDS,
		order_by="modified desc",
		limit_page_length=500,
	)
	parsed = [(row, _parse_assignees(row.get("_assign"))) for row in rows]
	all_assignees = {user for _, assignees in parsed for user in assignees}
	user_info = _user_info_map(all_assignees)
	return [
		_serialize_mis_row(row, assignees=assignees, user_info=user_info)
		for row, assignees in parsed
	]


@frappe.whitelist()
def get_monthly_implementation_summary(name):
	"""Return a single Monthly Implementation Summary for the SPA detail pane."""
	_require_mis_read()
	doc = frappe.get_doc(MIS_DOCTYPE, name)
	doc.check_permission("read")

	assignees = [a.get("owner") for a in get_assignments(MIS_DOCTYPE, doc.name)]
	return _serialize_mis_row(
		{
			"name": doc.name,
			"implementation": doc.implementation,
			"status": doc.status,
			"year": doc.year,
			"month": doc.month,
			"total_hours": doc.total_hours,
			"billable_hours": doc.billable_hours,
			"modified": doc.modified,
		},
		assignees=assignees,
		user_info=_user_info_map(assignees),
	)


@frappe.whitelist(methods=["POST"])
def set_monthly_implementation_summary_assignees(name, users=None):
	"""Replace MIS assignees with the given user list."""
	frappe.has_permission(MIS_DOCTYPE, "write", throw=True)
	doc = frappe.get_doc(MIS_DOCTYPE, name)
	doc.check_permission("write")

	desired = set(_parse_list(users))
	current = {a.get("owner") for a in get_assignments(MIS_DOCTYPE, name)}

	for user in current - desired:
		remove_assignment(MIS_DOCTYPE, name, user)

	to_add = list(desired - current)
	if to_add:
		description = " · ".join(
			part for part in (doc.implementation, doc.month, str(doc.year or "")) if part
		)
		add_assignment(
			{
				"doctype": MIS_DOCTYPE,
				"name": name,
				"assign_to": to_add,
				"description": description or doc.name,
			}
		)

	return get_monthly_implementation_summary(name)


@frappe.whitelist()
def get_timesheet_project_tasks(project=None):
	"""Return open Tasks for the Accounting standard project (start-modal dropdown)."""
	return dc.get_timesheet_project_tasks(CONFIG, project=project)


@frappe.whitelist()
def get_inbox(view="assigned", include_closed=0):
	"""Return Accounting-scoped Issues for the current user: assigned | created."""
	return dc.get_inbox(CONFIG, view=view, include_closed=include_closed)


@frappe.whitelist()
def get_issues(include_closed=0):
	"""Return all Accounting department Issues."""
	return dc.get_issues(CONFIG, include_closed=include_closed)


@frappe.whitelist()
def get_issue(name):
	"""Return Issue detail if it belongs to Accounting scope."""
	return dc.get_issue(CONFIG, name)


@frappe.whitelist()
def get_form_options():
	"""Form options scoped to Accounting department."""
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
	"""Create an Accounting-scoped Issue."""
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
	"""Update Issue status within Accounting scope."""
	return dc.update_status(CONFIG, name, status)


@frappe.whitelist(methods=["POST"])
def set_assignees(name, users=None):
	"""Replace Issue assignees within Accounting scope."""
	return dc.set_assignees(CONFIG, name, users=users)


@frappe.whitelist(methods=["POST"])
def update_issue(name, subject=None, description=None, priority=None, issue_type=None, project=None):
	"""Update whitelisted Issue fields within Accounting scope."""
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
	return dc.update_issue(CONFIG, name, **fields)


@frappe.whitelist()
def get_tasks(include_completed=0):
	"""Return Tasks for the Accounting department."""
	return dc.get_tasks(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_checklists(include_completed=0):
	"""Return Checklists linked to Accounting Issues/Tasks."""
	return dc.get_checklists(CONFIG, include_completed=include_completed)


@frappe.whitelist()
def get_task(name):
	"""Return Task detail for the Accounting SPA."""
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
):
	"""Update whitelisted Task fields within Accounting scope."""
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
	return dc.update_task(CONFIG, name, **fields)


@frappe.whitelist(methods=["POST"])
def set_task_assignees(name, users=None):
	"""Replace Task assignees within Accounting scope."""
	return dc.set_task_assignees(CONFIG, name, users=users)


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
	"""Create a Task in the Accounting department."""
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
	"""Convert an Issue into a Task (Accounting cockpit hand-off)."""
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
def add_task_dependency(name, depends_on):
	"""Add a predecessor dependency to a Task (Gantt link mode)."""
	return dc.add_task_dependency(CONFIG, name, depends_on)


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
	"""Update kanban status without deriving payment flags from column position."""
	doc.status = status
	if status == "Sent to DATEV":
		doc.sent_to_datev = 1
	# is_paid is not toggled by drag — use an explicit paid action elsewhere.


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


@frappe.whitelist(methods=["POST"])
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


def _receipt_extract_lock_key(name):
	return frappe.cache.make_key(f"accounting_receipt_extract_lock:{name}")


def _acquire_receipt_extract_lock(name):
	"""Atomic set-if-absent; True only for the caller that wins the race."""
	return bool(
		frappe.cache.set(_receipt_extract_lock_key(name), b"1", nx=True, ex=EXTRACT_CACHE_TTL)
	)


def _release_receipt_extract_lock(name):
	frappe.cache.delete(_receipt_extract_lock_key(name))


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
	finally:
		# Terminal state reached: allow the receipt to be re-extracted immediately.
		_release_receipt_extract_lock(accounting_receipt_name)


@frappe.whitelist(methods=["POST"])
def enqueue_receipt_pdf_extract(name):
	"""Queue background PDF extraction + auto-apply for a receipt opened in the SPA."""
	frappe.has_permission("Accounting Receipt", "write", throw=True)
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")

	attachment = (doc.attachment or "").strip()
	if not attachment or not attachment.lower().endswith(".pdf"):
		return {"queued": False, "reason": "no_attachment"}

	# Atomic claim: two concurrent callers can no longer both enqueue the same extract.
	if not _acquire_receipt_extract_lock(name):
		return {
			"queued": False,
			"reason": "already_running",
			"status": _get_receipt_extract_status(name),
		}

	try:
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
	except Exception:
		_release_receipt_extract_lock(name)
		raise

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
