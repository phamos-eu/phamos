# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employment Contracts in the Human Resources cockpit: KPIs, list, detail and editing.

Every call runs with the user's own permissions on Employment Contract, which only
HR Manager and System Manager have. HR Users can open the cockpit but get no access here.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_url_to_form, getdate, nowdate

from phamos.phamos.doctype.employment_contract.employment_contract import get_contract_history

DOCTYPE = "Employment Contract"
ENDING_SOON_DAYS = 60
LIST_FIELDS = (
	"name",
	"docstatus",
	"status",
	"employee",
	"employee_name",
	"company",
	"contract_type",
	"effective_from",
	"valid_until",
	"superseded_by",
	"fte_percentage",
	"full_time_hours_per_week",
	"weekly_hours",
	"currency",
	"yearly_gross_full_time",
	"monthly_amount",
	"monthly_gross",
	"expense_account",
	"notes",
)
EDITABLE_FIELDS = (
	"employee",
	"company",
	"contract_type",
	"effective_from",
	"valid_until",
	"fte_percentage",
	"full_time_hours_per_week",
	"currency",
	"yearly_gross_full_time",
	"monthly_amount",
	"expense_account",
	"notes",
)


@frappe.whitelist()
def get_access():
	"""Whether the cockpit should show the Contracts section to this user."""
	return {
		"can_read": bool(frappe.has_permission(DOCTYPE, "read")),
		"can_create": bool(frappe.has_permission(DOCTYPE, "create")),
	}


@frappe.whitelist()
def get_overview():
	"""KPI tiles and the three action lists for the Contracts overview."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	today = getdate(nowdate())
	horizon = add_days(today, ENDING_SOON_DAYS)

	submitted = frappe.get_list(DOCTYPE, filters={"docstatus": 1}, fields=list(LIST_FIELDS), limit_page_length=0)
	active = [c for c in submitted if in_force(c, today)]
	upcoming = sorted((c for c in submitted if getdate(c.effective_from) > today), key=lambda c: c.effective_from)
	ending = sorted(
		(c for c in active if c.valid_until and not c.superseded_by and getdate(c.valid_until) <= getdate(horizon)),
		key=lambda c: c.valid_until,
	)

	costs = {}
	for contract in active:
		costs[contract.currency] = costs.get(contract.currency, 0) + flt(contract.monthly_gross)

	covered = {c.employee for c in active} | {c.employee for c in upcoming}
	without_contract = [
		e
		for e in frappe.get_list(
			"Employee",
			filters={"status": "Active"},
			fields=["name as employee", "employee_name", "company"],
			order_by="employee_name asc",
			limit_page_length=0,
		)
		if e.employee not in covered
	]

	return {
		"today": str(today),
		"ending_soon_days": ENDING_SOON_DAYS,
		"active_fte": round(sum(flt(c.fte_percentage) for c in active) / 100, 2),
		"active_people": len(active),
		"external_people": sum(1 for c in active if c.contract_type == "External"),
		"monthly_cost": [{"currency": k, "amount": v} for k, v in sorted(costs.items(), key=lambda kv: -kv[1])],
		"ending_soon": ending,
		"upcoming": upcoming,
		"without_contract": without_contract,
		"drafts": frappe.db.count(DOCTYPE, {"docstatus": 0}),
	}


@frappe.whitelist()
def get_contracts():
	"""Draft and submitted contracts for the list; cancelled ones stay in Desk."""
	return frappe.get_list(
		DOCTYPE,
		filters={"docstatus": ("<", 2)},
		fields=list(LIST_FIELDS),
		order_by="employee_name asc, effective_from desc",
		limit_page_length=0,
	)


@frappe.whitelist()
def get_contract(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	data = {field: doc.get(field) for field in LIST_FIELDS}
	data["desk_url"] = get_url_to_form(DOCTYPE, name)
	data["history"] = get_contract_history(doc.employee)
	data["can_record_change"] = bool(
		doc.docstatus == 1
		and doc.status in ("Active", "Upcoming")
		and not doc.superseded_by
		and frappe.has_permission(DOCTYPE, "create")
	)
	data["can_edit"] = bool(doc.docstatus == 0 and doc.has_permission("write"))
	return data


@frappe.whitelist(methods=["POST"])
def save_contract(values, name=None, submit=0):
	"""Create a contract, or update a draft, and optionally submit it in the same step."""
	values = frappe.parse_json(values) or {}
	clean = {k: values.get(k) for k in EDITABLE_FIELDS if k in values}

	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		if doc.docstatus != 0:
			frappe.throw(_("Only draft contracts can be edited. Record a change instead."))
		doc.update(clean)
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.update(clean)

	if doc.employee and not doc.company:
		doc.company = frappe.db.get_value("Employee", doc.employee, "company")
	if doc.company and not doc.currency:
		doc.currency = frappe.get_cached_value("Company", doc.company, "default_currency")

	doc.save()
	if frappe.utils.cint(submit):
		doc.submit()
	return get_contract(doc.name)


@frappe.whitelist(methods=["POST"])
def submit_contract(name):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.submit()
	return get_contract(doc.name)


@frappe.whitelist()
def get_employee_defaults(employee):
	"""Company and currency for a new contract, plus the employee's latest contract to copy terms from."""
	frappe.has_permission(DOCTYPE, "create", throw=True)
	company = frappe.db.get_value("Employee", employee, "company")
	latest = frappe.get_list(
		DOCTYPE,
		filters={"employee": employee, "docstatus": 1},
		fields=list(LIST_FIELDS),
		order_by="effective_from desc",
		limit_page_length=1,
	)
	return {
		"company": company,
		"currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
		"latest": latest[0] if latest else None,
	}


def in_force(contract, on_date):
	return getdate(contract.effective_from) <= on_date and (
		not contract.valid_until or getdate(contract.valid_until) >= on_date
	)
