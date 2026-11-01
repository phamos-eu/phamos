# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

"""Employment Contracts in the Human Resources cockpit: KPIs, list, detail and editing.

Every call runs with the user's own permissions on Employment Contract, which only
HR Manager and System Manager have. HR Users can open the cockpit but get no access here.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, get_url_to_form, getdate, nowdate

from phamos.api.project_management_spa import ACTIVE_IMPLEMENTATION_STATUSES
from phamos.phamos.doctype.employment_contract.employment_contract import get_contract_history

DOCTYPE = "Employment Contract"
ENDING_SOON_DAYS = 60
# The monthly chart on the overview: 8 months back, the current month and 3 months ahead.
TREND_MONTHS_BACK = 8
TREND_MONTHS_AHEAD = 3
# Contract hours per week become hours per month at 52 weeks over 12 months (#1800).
# Gross: leave and sick leave are not deducted yet (#1802).
WEEKS_PER_MONTH = 52 / 12
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
	"company_currency",
	"conversion_rate",
	"base_monthly_gross",
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
	"conversion_rate",
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

	# Company currency at each contract's fixed planning rate, so the total does not move
	# with daily exchange rates. Grouped per company currency for multi-company sites.
	costs = {}
	for contract in active:
		currency = contract.company_currency or contract.currency
		costs[currency] = costs.get(currency, 0) + flt(contract.base_monthly_gross)

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

	drafts = frappe.get_list(DOCTYPE, filters={"docstatus": 0}, fields=list(LIST_FIELDS), limit_page_length=0)
	main_currency = max(costs, key=costs.get) if costs else None

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
		"drafts": len(drafts),
		"trend": {
			"currency": main_currency,
			"months": add_implementation_hours(monthly_trend(today, submitted, drafts, main_currency)),
		},
	}


def monthly_trend(today, submitted, drafts, currency):
	"""FTE and monthly cost per month, from TREND_MONTHS_BACK months ago to TREND_MONTHS_AHEAD ahead.

	A month counts the contracts in force on its 1st; the current month uses today, so it
	matches the KPI tiles. Future months add drafts as an estimate: a draft takes the place
	of the employee's submitted contract from its start date, as it will on submit, so a
	planned change is not counted twice. Cost counts contracts in `currency` only (the main
	company currency); FTE counts every contract.
	"""
	this_month = get_first_day(today)
	# Sorted by start, so the latest-starting draft wins when an employee has several.
	drafts = sorted(drafts, key=lambda d: getdate(d.effective_from))
	months = []
	for offset in range(-TREND_MONTHS_BACK, TREND_MONTHS_AHEAD + 1):
		month = add_months(this_month, offset)
		day = today if offset == 0 else month
		confirmed = {c.employee: c for c in submitted if in_force(c, day)}
		estimated = {d.employee: d for d in drafts if in_force(d, day)} if offset > 0 else {}
		for employee in estimated:
			confirmed.pop(employee, None)
		months.append(
			{
				"month": str(month),
				"is_current": offset == 0,
				"is_future": offset > 0,
				"fte": total_fte(confirmed.values()),
				"cost": total_cost(confirmed.values(), currency),
				"estimate_fte": total_fte(estimated.values()),
				"estimate_cost": total_cost(estimated.values(), currency),
				"capacity_hours": total_hours(confirmed.values()),
				"estimate_capacity_hours": total_hours(estimated.values()),
			}
		)
	return months


def total_fte(contracts):
	return round(sum(flt(c.fte_percentage) for c in contracts) / 100, 2)


def total_hours(contracts):
	return round(sum(flt(c.weekly_hours) for c in contracts) * WEEKS_PER_MONTH, 1)


def total_cost(contracts, currency):
	return round(sum(flt(c.base_monthly_gross) for c in contracts if (c.company_currency or c.currency) == currency), 2)


def add_implementation_hours(months):
	"""Add the hours worked and predicted on Implementations to each month of the trend.

	Past months and the current one get `spent_hours`; future months get `predicted_hours`.
	HR Managers cannot read Implementation, but see these sums anyway (#1800): the queries
	skip permissions and return monthly totals only, never a single Implementation.
	"""
	keys = [m["month"][:7] for m in months]
	past = [m["month"][:7] for m in months if not m["is_future"]]
	future = [m["month"][:7] for m in months if m["is_future"]]
	spent = spent_hours_by_month(past[0], past[-1]) if past else {}
	predicted = predicted_hours_by_month(future)
	for month, key in zip(months, keys):
		month["spent_hours"] = None if month["is_future"] else round(spent.get(key, 0), 1)
		month["predicted_hours"] = round(predicted.get(key, 0), 1) if month["is_future"] else None
	return months


def spent_hours_by_month(first_key, last_key):
	"""Timesheet hours, billable or not, on projects that belong to an Implementation.

	Read from Timesheets rather than the Implementation's Resource planning table, which
	only refreshes when the Implementation is saved. Months follow the Timesheet's start
	date, like Resource planning. Cancelled Timesheets don't count.
	"""
	rows = frappe.db.sql(
		"""
		SELECT DATE_FORMAT(ts.start_date, '%%Y-%%m') AS month, SUM(tsd.hours) AS hours
		FROM `tabTimesheet Detail` tsd
		JOIN `tabTimesheet` ts ON ts.name = tsd.parent
		JOIN `tabProject` p ON p.name = tsd.project
		WHERE ts.docstatus < 2
			AND IFNULL(p.custom_implementation, '') != ''
			AND ts.start_date BETWEEN %s AND %s
		GROUP BY month
		""",
		(f"{first_key}-01", get_last_day(f"{last_key}-01")),
		as_dict=True,
	)
	return {r.month: flt(r.hours) for r in rows}


def predicted_hours_by_month(keys):
	"""Predicted hours per month (`YYYY-MM`) over all active Implementations.

	An Implementation with several predictions for one month counts their average, as
	`Implementation.predicted_time_next_3_months` does. Completed and Cancelled
	Implementations don't count.
	"""
	if not keys:
		return {}
	rows = frappe.get_all(
		"Prediction",
		filters={
			"parenttype": "Implementation",
			"parentfield": "resource_planning_prediction",
			"month_and_year": ("in", keys),
		},
		fields=["parent", "month_and_year", "prediction"],
	)
	active = set(
		frappe.get_all(
			"Implementation",
			filters={"name": ("in", list({r.parent for r in rows})), "status": ("in", ACTIVE_IMPLEMENTATION_STATUSES)},
			pluck="name",
		)
		if rows
		else []
	)
	values = {}
	for row in rows:
		if row.parent in active:
			values.setdefault((row.parent, row.month_and_year), []).append(flt(row.prediction))
	totals = {}
	for (_parent, key), predictions in values.items():
		totals[key] = totals.get(key, 0) + sum(predictions) / len(predictions)
	return totals


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
	data["can_delete"] = bool(doc.docstatus == 0 and doc.has_permission("delete"))
	return data


@frappe.whitelist(methods=["POST"])
def save_contract(values, name=None, submit=0):
	"""Create a contract, or update a draft, and optionally submit it in the same step."""
	values = frappe.parse_json(values) or {}
	clean = {k: values.get(k) for k in EDITABLE_FIELDS if k in values}

	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		# Permission first, so a user without access learns nothing about the contract.
		doc.check_permission("write")
		if doc.docstatus != 0:
			frappe.throw(_("Only draft contracts can be edited. Record a change instead."))
		doc.update(clean)
	else:
		doc = frappe.new_doc(DOCTYPE)
		doc.update(clean)

	# New documents come pre-filled with the user's default company and the site's default
	# currency; a contract belongs to the employee's company and starts in its currency.
	if doc.employee:
		doc.company = frappe.db.get_value("Employee", doc.employee, "company")
	if doc.is_new() and doc.company and not values.get("currency"):
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


@frappe.whitelist(methods=["POST"])
def delete_contract(name):
	"""Delete a draft contract.

	Submitted contracts are history that capacity and cost rely on: they are changed with
	Record change, or cancelled in Desk, but never deleted from the cockpit.
	"""
	doc = frappe.get_doc(DOCTYPE, name)
	# Permission first, so a user without access learns nothing about the contract.
	doc.check_permission("delete")
	if doc.docstatus != 0:
		frappe.throw(_("Only draft contracts can be deleted."))
	frappe.delete_doc(DOCTYPE, name)


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
