# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.utils import add_months, get_first_day, getdate, today

from phamos.phamos.doctype.monthly_implementation_summary.monthly_implementation_summary import (
	_get_month_date_range,
)

_MONTH_NAMES = (
	"January",
	"February",
	"March",
	"April",
	"May",
	"June",
	"July",
	"August",
	"September",
	"October",
	"November",
	"December",
)

def _mis_creation_logger():
	return frappe.logger("phamos.mis_creation", allow_site=True)


def _mis_rows_for_impl_period(implementation, year_str, month_name):
	"""All MIS rows for this implementation + calendar period (any docstatus)."""
	y = str(year_str or "").strip()
	m = (month_name or "").strip()
	return frappe.get_all(
		"Monthly Implementation Summary",
		filters={"implementation": implementation, "year": y, "month": m},
		fields=["name", "docstatus"],
		order_by="modified desc",
	)


def _blocking_mis_rows(period_rows):
	"""Draft (0) or submitted (1) block creating another MIS; cancelled (2) does not."""
	out = []
	for r in period_rows or []:
		try:
			ds = int(r.get("docstatus") if r.get("docstatus") is not None else -1)
		except (TypeError, ValueError):
			continue
		if ds in (0, 1):
			out.append(r)
	return out


def _skip_reason_for_blocking(blocking_rows):
	if not blocking_rows:
		return None
	statuses = set()
	for r in blocking_rows:
		try:
			statuses.add(int(r.get("docstatus") if r.get("docstatus") is not None else -1))
		except (TypeError, ValueError):
			continue
	if statuses == {0}:
		return "draft_mis_already_exists"
	if statuses == {1}:
		return "submitted_mis_already_exists"
	return "active_mis_already_exists"


def _docstatus_int(row, key="docstatus"):
	try:
		return int(row.get(key) if row.get(key) is not None else -1)
	except (TypeError, ValueError):
		return -1


def _docstatus_label(ds: int) -> str:
	return {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(ds, f"docstatus_{ds}")


def _why_skipped_existing_mis(
	implementation: str, month_name: str, year_str: str, blocking_rows: list
) -> str:
	parts = []
	for b in blocking_rows:
		ds = _docstatus_int(b)
		parts.append(f"{b.get('name')} ({_docstatus_label(ds)})")
	docs = ", ".join(parts)
	return (
		f"Not created: active Monthly Implementation Summary already exists for "
		f"{implementation}, {month_name} {year_str}: {docs}. "
		f"Cancel or amend that document if you need a new summary for the same period."
	)


def _why_skipped_no_timesheets(audit: dict) -> str:
	code = audit.get("reason") or ""
	if code == "no_projects_linked_to_implementation":
		return (
			f"No summary for {audit.get('implementation')}: "
			"link at least one Project to this Implementation "
			"(custom_implementation) so timesheets can be found."
		)
	if code == "invalid_month_year_range":
		return "No summary: invalid month or year for the selected period."
	if code == "no_timesheets_non_cancelled_in_period_on_implementation_projects":
		return (
			f"No summary for {audit.get('implementation')}: "
			f"no non-cancelled timesheets in {audit.get('month')} {audit.get('year')} "
			f"on its projects ({audit.get('from_date')} – {audit.get('to_date')})."
		)
	return f"No summary: {code or 'no qualifying timesheets'}."


def _implementation_timesheet_audit(implementation, mis_year_str, mis_month_name):
	"""
	Returns (eligible: bool, detail: dict) for MIS creation.
	detail explains date range, projects, matching timesheets, and reason if not eligible.
	"""
	detail = {
		"implementation": implementation,
		"year": str(mis_year_str),
		"month": mis_month_name,
		"from_date": None,
		"to_date": None,
		"projects": [],
		"timesheets_in_period": [],
		"eligible": False,
		"reason": None,
	}
	from_date, to_date = _get_month_date_range(mis_year_str, mis_month_name)
	detail["from_date"] = str(from_date) if from_date else None
	detail["to_date"] = str(to_date) if to_date else None
	if not from_date or not to_date:
		detail["reason"] = "invalid_month_year_range"
		return False, detail

	projects = frappe.get_all(
		"Project", filters={"custom_implementation": implementation}, pluck="name"
	)
	detail["projects"] = list(projects or [])
	if not detail["projects"]:
		detail["reason"] = "no_projects_linked_to_implementation"
		return False, detail

	TS = DocType("Timesheet")
	TD = DocType("Timesheet Detail")
	Emp = DocType("Employee")
	rows = (
		frappe.qb.from_(TS)
		.inner_join(TD).on(TD.parent == TS.name)
		.inner_join(Emp).on(Emp.name == TS.employee)
		.select(TS.name)
		.distinct()
		.where(TD.project.isin(projects))
		.where(TS.docstatus != 2)
		.where(TS.start_date.between(from_date, to_date))
	).run()

	names = sorted({r[0] for r in rows if r and r[0]})
	detail["timesheets_in_period"] = names
	if not names:
		detail["reason"] = (
			"no_timesheets_non_cancelled_in_period_on_implementation_projects"
		)
		return False, detail

	detail["eligible"] = True
	detail["reason"] = "has_timesheets_in_period"
	return True, detail


def _run_mis_creation_for_period(sched_year_str, sched_month_name):
	"""
	Create Monthly Implementation Summary for each **active** Implementation
	(any status except **Completed** or **Cancelled**) that has at least one
	non-cancelled timesheet in the given calendar month.

	The MIS ``year`` / ``month`` match that period; on insert, ``set_timesheets_table``
	uses the same date range so all timesheets falling in that month (on the impl’s
	projects) are loaded.

	Skips when a non-cancelled MIS already exists (draft or submitted).

	Logs each implementation to bench/site log: phamos.mis_creation.log
	"""
	implementations = frappe.get_all(
		"Implementation",
		filters={
		   "status": ["not in", ["Completed", "Cancelled"]],
		   "customer": ["!=", "Knd-00000"],},
		fields=["name"],
	)

	log = _mis_creation_logger()
	log.warning(
		"MIS creation run start | period=%s %s | active_implementations=%s",
		sched_month_name,
		sched_year_str,
		len(implementations),
	)

	created_count = 0
	skipped_count = 0
	skipped_no_timesheets = 0
	error_count = 0
	impl_log_lines = []

	for impl in implementations:
		try:
			ok, audit = _implementation_timesheet_audit(
				impl.name, str(sched_year_str), sched_month_name
			)
			if not ok:
				skipped_no_timesheets += 1
				line = (
					f"SKIP no_timesheets | impl={audit['implementation']} | "
					f"{json.dumps(audit, default=str)}"
				)
				log.warning(line)
				impl_log_lines.append(
					{
						"implementation": impl.name,
						"action": "skip",
						"reason": audit.get("reason"),
						"why_skipped": _why_skipped_no_timesheets(audit),
					}
				)
				continue

			log.warning(
				"TIMESHEETS selected | impl=%s | count=%s | names=%s | range=%s..%s | projects=%s",
				impl.name,
				len(audit["timesheets_in_period"]),
				audit["timesheets_in_period"],
				audit["from_date"],
				audit["to_date"],
				audit["projects"],
			)

			period_mis = _mis_rows_for_impl_period(
				impl.name, str(sched_year_str), sched_month_name
			)
			blocking = _blocking_mis_rows(period_mis)
			if blocking:
				skipped_count += 1
				reason = _skip_reason_for_blocking(blocking)
				line = (
					f"SKIP {reason} | impl={impl.name} | period={sched_month_name} {sched_year_str} | "
					f"blocking={blocking} | all_period_mis={period_mis}"
				)
				log.warning(line)
				impl_log_lines.append(
					{
						"implementation": impl.name,
						"action": "skip",
						"reason": reason,
						"why_skipped": _why_skipped_existing_mis(
							impl.name, sched_month_name, str(sched_year_str), blocking
						),
						"blocking_mis": [
							{
								"name": b["name"],
								"docstatus": _docstatus_int(b),
								"status": _docstatus_label(_docstatus_int(b)),
							}
							for b in blocking
						],
					}
				)
				continue

			doc = frappe.get_doc(
				{
					"doctype": "Monthly Implementation Summary",
					"implementation": impl.name,
					"year": str(sched_year_str),
					"month": sched_month_name,
				}
			)
			doc.insert()

			created_count += 1
			log.warning(
				"CREATED mis=%s | impl=%s | period=%s %s",
				doc.name,
				impl.name,
				sched_month_name,
				sched_year_str,
			)
			impl_log_lines.append(
				{
					"implementation": impl.name,
					"action": "created",
					"mis": doc.name,
					"timesheets_in_period": audit["timesheets_in_period"],
				}
			)
			frappe.db.commit()

		except Exception:
			error_count += 1
			frappe.db.rollback()
			log.exception(
				"MIS creation ERROR | impl=%s | period=%s %s",
				impl.name,
				sched_month_name,
				sched_year_str,
			)
			impl_log_lines.append(
				{
					"implementation": impl.name,
					"action": "error",
					"reason": "exception_on_insert",
				}
			)

	log.warning(
		"MIS creation run end | created=%s skipped_existing=%s skipped_no_timesheets=%s errors=%s",
		created_count,
		skipped_count,
		skipped_no_timesheets,
		error_count,
	)

	return {
		"created": created_count,
		"skipped_existing": skipped_count,
		"skipped_no_timesheets": skipped_no_timesheets,
		"errors": error_count,
		"details": impl_log_lines,
	}


def create_monthly_implementation_summaries():
	"""
	Registered in ``hooks.scheduler_events`` under **daily**; this function no-ops
	unless **today is the 1st** of the month (server ``today()``).

	**Period:** previous calendar month. Example: on **1 April** → create MIS for
	**March** (same year); on **1 January** → **December** of the **previous**
	year.

	**Eligibility:** active Implementation = not Completed / Cancelled; at least
	one non-cancelled Timesheet with ``start_date`` in that month on a Project
	linked to the Implementation.

	**MIS content:** ``year`` and ``month`` on the new MIS match that period;
	``set_timesheets_table`` (on validate) uses the same month date range, so all
	March timesheets load for a March MIS.
	"""
	today_date = getdate(today())

	if today_date.day != 1:
		return

	first_this_month = get_first_day(today_date)
	prev_month_anchor = add_months(first_this_month, -1)
	sched_year = prev_month_anchor.year
	sched_month_name = _MONTH_NAMES[prev_month_anchor.month - 1]

	_run_mis_creation_for_period(str(sched_year), sched_month_name)


@frappe.whitelist()
def run_manual_mis_creation(month, year):
	"""
	From phamos Settings: same logic as the scheduled job, for a chosen month/year.
	Creates Monthly Implementation Summary rows (not Implementation master records).
	Response includes `details` per active implementation (skip reason).
	"""
	frappe.only_for("System Manager")

	month = (month or "").strip()
	year = str(year or "").strip()

	if not month or not year:
		frappe.throw(_("Month and Year are required"))

	if month not in _MONTH_NAMES:
		frappe.throw(_("Invalid month"))

	return _run_mis_creation_for_period(year, month)
