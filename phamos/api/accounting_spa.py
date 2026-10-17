# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Accounting SPA API — department-scoped Issues/Tasks and Accounting Receipts."""

import frappe
from frappe import _
from frappe.desk.form.assign_to import add as add_assignment
from frappe.desk.form.assign_to import remove as remove_assignment
from frappe.desk.form.load import get_assignments
from frappe.utils import flt, get_fullname

from phamos.accounting.pdf_stamp import note_to_lines
from phamos.api import department_cockpit as dc
from phamos.api.accounting_stats import can_read_statistics
from phamos.api.issue_common import _parse_assignees, _parse_list

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
	settings["can_read_statistics"] = 1 if can_read_statistics() else 0
	settings["can_read_ai_skills"] = 1 if frappe.has_permission("AI Skill", "read") else 0
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


@frappe.whitelist()
def get_issue_chat(name):
	"""Return the Raven chat state of an Issue in Accounting scope."""
	return dc.get_issue_chat(CONFIG, name)


@frappe.whitelist(methods=["POST"])
def ensure_issue_chat(name):
	"""Start or join the Raven chat of an Issue in Accounting scope."""
	return dc.ensure_issue_chat(CONFIG, name)


@frappe.whitelist()
def get_issue_chat_states(names):
	"""Return the chat state per Issue for list views."""
	return dc.get_issue_chat_states(names)


@frappe.whitelist(methods=["POST"])
def start_issue_dm(name, user):
	"""Open the Raven DM with a user, carrying a link to an Issue in Accounting scope."""
	return dc.start_issue_dm(CONFIG, name, user)


@frappe.whitelist(methods=["POST"])
def update_issue(
	name, subject=None, description=None, priority=None, issue_type=None, project=None, modified=None
):
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
	if modified is not None:
		fields["modified"] = modified
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
	modified=None,
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
	if modified is not None:
		fields["modified"] = modified
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
	"attachment",
	"modified",
]

# Setting this status directly would claim a send that did not happen.
RECEIPT_STATUSES_NOT_DROPPABLE = {
	"Sent to DATEV": "Use Send to DATEV; the status follows when the e-mail is queued.",
}


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
	"""Move the receipt to a kanban column.

	Dropping on Paid records the payment (today unless a payment date is already set).
	Leaving Paid does not clear is_paid: a payment that happened stays recorded.
	"""
	doc.status = status
	if status == "Paid":
		doc.is_paid = 1
		if not doc.payment_date:
			doc.payment_date = frappe.utils.today()


@frappe.whitelist()
def get_receipts():
	"""Return Accounting Receipts for the Receipts kanban."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)

	rows = frappe.get_list(
		"Accounting Receipt",
		fields=RECEIPT_LIST_FIELDS,
		filters={"status": ("!=", "Cancelled")},
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
	row = _serialize_receipt_row(
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
	row["note_text"] = "\n".join(note_to_lines(doc.note))
	row.update(
		{
			"due_date": doc.due_date,
			"net_total": doc.net_total,
			"total_taxes": doc.total_taxes,
			"supplier_tax_id": doc.supplier_tax_id,
			"supplier_iban": doc.supplier_iban,
			"payment_reference": doc.payment_reference,
			"payment_date": doc.payment_date,
			"project": doc.project,
			"cost_center": doc.cost_center,
			"company": doc.company,
			"purchase_invoice": doc.purchase_invoice,
			"purchase_invoice_status": frappe.db.get_value("Purchase Invoice", doc.purchase_invoice, "status") if doc.purchase_invoice else None,
			"purchase_invoice_docstatus": frappe.db.get_value("Purchase Invoice", doc.purchase_invoice, "docstatus") if doc.purchase_invoice else None,
			"payment_request": doc.payment_request,
			"employee": doc.get("employee"),
			"expense_claim": doc.get("expense_claim"),
			"expense_claim_status": frappe.db.get_value("Expense Claim", doc.expense_claim, "status") if doc.get("expense_claim") else None,
			"journal_entry": doc.get("journal_entry"),
			"journal_entry_docstatus": frappe.db.get_value("Journal Entry", doc.journal_entry, "docstatus") if doc.get("journal_entry") else None,
			"payment_request_status": frappe.db.get_value("Payment Request", doc.payment_request, "status") if doc.payment_request else None,
			"mode_of_payment": doc.mode_of_payment,
			"bank_account": doc.bank_account,
			"items": [
				{
					"name": i.name,
					"item_name": i.item_name,
					"qty": i.qty,
					"rate": i.rate,
					"amount": i.amount,
					"tax_rate": i.tax_rate,
					"expense_account": i.expense_account,
					"assignment_source": i.assignment_source,
					"assignment": i.assignment,
					"assignment_validation": frappe.db.get_value("Account Assignment", i.assignment, "validation") if i.assignment else None,
					"ai_expense_account": i.ai_expense_account,
					"ai_confidence": i.ai_confidence,
					"ai_reason": i.ai_reason,
					"ai_candidates": frappe.parse_json(i.ai_candidates) if i.ai_candidates else [],
				}
				for i in doc.items
			],
			"ai": _ai_block(doc),
		}
	)
	return row


def _ai_block(doc):
	"""Summary, confidence and flags of the receipt's latest AI run."""
	flags = []
	if doc.ai_run:
		raw = frappe.db.get_value("AI Agent Run", doc.ai_run, "run_flags")
		flags = frappe.parse_json(raw or "[]") or []
	return {"run": doc.ai_run, "summary": doc.ai_summary, "confidence": doc.ai_confidence, "flags": flags,
		"decision": doc.get("ai_decision")}


@frappe.whitelist(methods=["POST"])
def update_receipt_status(name, status):
	"""Update Accounting Receipt status from kanban drag."""
	frappe.has_permission("Accounting Receipt", "write", throw=True)
	status = (status or "").strip()
	if status not in RECEIPT_KANBAN_STATUSES:
		frappe.throw(_("Invalid status: {0}").format(status))
	if status in RECEIPT_STATUSES_NOT_DROPPABLE:
		frappe.throw(_(RECEIPT_STATUSES_NOT_DROPPABLE[status]))

	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	_apply_receipt_status_flags(doc, status)
	doc.save()
	return get_receipt(name)


RUN_STATUS_TO_EXTRACT_STATE = {"Queued": "running", "Running": "running", "Completed": "done", "Failed": "failed"}


def _extract_state(name):
	"""Extraction state of a receipt from its latest AI Agent Run."""
	from phamos.ai_agents.runner import latest_run

	run_name = latest_run("Accounting Receipt", name)
	if not run_name:
		return {"status": "idle"}
	run = frappe.db.get_value(
		"AI Agent Run", run_name, ["name", "status", "fields_set", "error", "summary", "confidence"], as_dict=True
	)
	return {
		"status": RUN_STATUS_TO_EXTRACT_STATE.get(run.status, "idle"),
		"run": run.name,
		"updated": [f.strip() for f in (run.fields_set or "").split(",") if f.strip()],
		"message": run.error,
		"summary": run.summary,
		"confidence": run.confidence,
	}


@frappe.whitelist(methods=["POST"])
def enqueue_receipt_pdf_extract(name, overwrite=0):
	"""Queue the AI Accountant for a receipt. Fills empty fields; overwrite=1 replaces values."""
	frappe.has_permission("Accounting Receipt", "write", throw=True)
	doc = frappe.get_doc("Accounting Receipt", name)
	doc.check_permission("write")
	if not (doc.attachment or "").strip().lower().endswith(".pdf"):
		return {"queued": False, "reason": "no_attachment"}

	from phamos.ai_agents.runner import enqueue_run

	result = enqueue_run(
		"Accounting Receipt", name, trigger="Manual", mode="Overwrite" if frappe.utils.cint(overwrite) else "Fill Empty"
	)
	if not result.get("queued") and result.get("reason") == "no_agent":
		frappe.throw(_("No enabled AI Agent works on Accounting Receipts."))
	return {**result, "status": _extract_state(name)}


@frappe.whitelist()
def get_receipt_extract_status(name):
	"""Extraction state for the cockpit (from the latest AI Agent Run)."""
	frappe.has_permission("Accounting Receipt", "read", throw=True)
	frappe.get_doc("Accounting Receipt", name).check_permission("read")
	return _extract_state(name)
