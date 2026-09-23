# Copyright (c) 2026, phamos.eu and contributors
# One-off local seed: Implementations + Projects + monthly Timesheets for MIS playground.
# Run: bench --site erpnext.local execute phamos.scripts.seed_mis_playground.run

from __future__ import annotations

import random
from datetime import datetime

import frappe
from frappe.utils import add_to_date, flt, get_datetime

SEED_TAG = "MIS-SEED"
YEAR = 2026
MONTHS = range(1, 10)  # January–September 2026
IMPL_SPECS = [
	{
		"customer_name": f"{SEED_TAG} Acme Consulting",
		"impl_name": f"{SEED_TAG} Acme",
		"project_name": f"{SEED_TAG} Acme Delivery",
		"billable_ratio_range": (0.85, 1.0),  # mostly green deltas
	},
	{
		"customer_name": f"{SEED_TAG} Northwind GmbH",
		"impl_name": f"{SEED_TAG} Northwind",
		"project_name": f"{SEED_TAG} Northwind Rollout",
		"billable_ratio_range": (0.7, 0.9),  # mixed amber
	},
	{
		"customer_name": f"{SEED_TAG} Contoso AG",
		"impl_name": f"{SEED_TAG} Contoso",
		"project_name": f"{SEED_TAG} Contoso Support",
		"billable_ratio_range": (0.5, 0.75),  # often red deltas
	},
]


def _pick_company():
	return (
		frappe.db.get_single_value("Global Defaults", "default_company")
		or frappe.db.get_value("Company", {}, "name")
	)


def _pick_customer_group():
	return (
		frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
		or frappe.db.get_value("Customer Group", {}, "name")
	)


def _pick_territory():
	return (
		frappe.db.get_value("Territory", {"is_group": 0}, "name")
		or frappe.db.get_value("Territory", {}, "name")
	)


def _pick_employees(limit=4):
	rows = frappe.get_all(
		"Employee",
		filters={"status": "Active"},
		fields=["name", "employee_name"],
		limit_page_length=limit,
	)
	if not rows:
		frappe.throw("No Active Employee found — create at least one Employee first.")
	return rows


def _pick_activity_type():
	name = frappe.db.get_value("Activity Type", {}, "name")
	if not name:
		frappe.throw("No Activity Type found — create at least one Activity Type first.")
	return name


def _pick_account_manager():
	return (
		frappe.db.get_value(
			"User",
			{"enabled": 1, "user_type": "System User", "name": ("!=", "Administrator")},
			"name",
		)
		or "Administrator"
	)


def _ensure_customer(customer_name, customer_group, territory):
	existing = frappe.db.get_value("Customer", {"customer_name": customer_name}, "name")
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": customer_name,
			"customer_type": "Company",
			"customer_group": customer_group,
			"territory": territory,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_implementation(impl_name, customer, account_manager):
	if frappe.db.exists("Implementation", impl_name):
		doc = frappe.get_doc("Implementation", impl_name)
		if not doc.account_manager:
			doc.account_manager = account_manager
			doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc(
		{
			"doctype": "Implementation",
			"name": impl_name,
			"customer": customer,
			"status": "Open",
			"start_date": f"{YEAR}-01-01",
			"account_manager": account_manager,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_project(project_name, company, customer, implementation, project_owner):
	existing = frappe.db.get_value("Project", {"project_name": project_name}, "name")
	if existing:
		doc = frappe.get_doc("Project", existing)
		changed = False
		if doc.get("custom_implementation") != implementation:
			doc.custom_implementation = implementation
			changed = True
		if doc.customer != customer:
			doc.customer = customer
			changed = True
		if changed:
			doc.save(ignore_permissions=True)
		return doc.name

	payload = {
		"doctype": "Project",
		"project_name": project_name,
		"company": company,
		"customer": customer,
		"status": "Open",
		"custom_implementation": implementation,
	}
	if frappe.get_meta("Project").has_field("project_owner"):
		payload["project_owner"] = project_owner
	doc = frappe.get_doc(payload)
	doc.insert(ignore_permissions=True)
	return doc.name


def _timesheet_already_seeded(project, month):
	"""Detect prior seed rows for this project/month via note prefix."""
	prefix = f"{SEED_TAG} {YEAR}-{month:02d}"
	return frappe.db.count(
		"Timesheet",
		filters={
			"parent_project": project,
			"note": ("like", f"{prefix}%"),
			"docstatus": ("<", 2),
		},
	)


def _create_timesheet(
	*,
	company,
	employee,
	customer,
	project,
	activity,
	start,
	hours,
	billing_hours,
	note,
):
	end = add_to_date(start, hours=hours, as_datetime=True)
	doc = frappe.get_doc(
		{
			"doctype": "Timesheet",
			"company": company,
			"employee": employee,
			"customer": customer,
			"parent_project": project,
			"note": note,
			"time_logs": [
				{
					"activity_type": activity,
					"from_time": start,
					"to_time": end,
					"hours": hours,
					"is_billable": 1 if billing_hours > 0 else 0,
					"billing_hours": billing_hours,
					"project": project,
					"description": note,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _create_month_timesheets(spec, *, company, customer, project, employees, activity, month):
	existing = _timesheet_already_seeded(project, month)
	if existing:
		return {"created": 0, "skipped_existing": existing}

	rng = random.Random(f"{SEED_TAG}-{spec['impl_name']}-{YEAR}-{month}")
	count = rng.randint(5, 20)
	created = []
	low, high = spec["billable_ratio_range"]

	for i in range(count):
		day = rng.randint(1, 28)
		hour = rng.randint(8, 16)
		start = get_datetime(f"{YEAR}-{month:02d}-{day:02d} {hour:02d}:00:00")
		hours = round(rng.uniform(1.0, 8.0), 2)
		ratio = rng.uniform(low, high)
		billing_hours = round(flt(hours) * ratio, 2)
		employee = rng.choice(employees)["name"]
		note = f"{SEED_TAG} {YEAR}-{month:02d} #{i + 1} {spec['impl_name']}"
		name = _create_timesheet(
			company=company,
			employee=employee,
			customer=customer,
			project=project,
			activity=activity,
			start=start,
			hours=hours,
			billing_hours=billing_hours,
			note=note,
		)
		created.append(name)

	return {"created": len(created), "skipped_existing": 0, "names": created}


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

MIS_NAMING_SERIES = "MIS-.YYYY.-.#####"


def _ensure_mis_naming_series():
	"""Local sites often lack MIS naming-series options; set a usable default."""
	meta = frappe.get_meta("Monthly Implementation Summary")
	df = meta.get_field("naming_series")
	if not df:
		return MIS_NAMING_SERIES

	options = [o.strip() for o in (df.options or "").split("\n") if o.strip()]
	if MIS_NAMING_SERIES not in options:
		options = [MIS_NAMING_SERIES] + options
		frappe.db.set_value(
			"DocField",
			{"parent": "Monthly Implementation Summary", "fieldname": "naming_series"},
			"options",
			"\n".join(options),
		)
		frappe.clear_cache(doctype="Monthly Implementation Summary")
	return MIS_NAMING_SERIES


def create_mis_records():
	"""Create one MIS per seeded Implementation × month (Jan–Sep)."""
	frappe.set_user("Administrator")
	series = _ensure_mis_naming_series()
	created = []
	skipped = []
	errors = []

	for spec in IMPL_SPECS:
		impl = spec["impl_name"]
		if not frappe.db.exists("Implementation", impl):
			errors.append({"implementation": impl, "error": "missing_implementation"})
			continue
		for month in MONTHS:
			month_name = _MONTH_NAMES[month - 1]
			existing = frappe.db.exists(
				"Monthly Implementation Summary",
				{"implementation": impl, "year": str(YEAR), "month": month_name, "docstatus": ("<", 2)},
			)
			if existing:
				skipped.append({"implementation": impl, "month": month_name, "name": existing})
				continue
			try:
				doc = frappe.get_doc(
					{
						"doctype": "Monthly Implementation Summary",
						"naming_series": series,
						"implementation": impl,
						"year": str(YEAR),
						"month": month_name,
					}
				)
				doc.insert(ignore_permissions=True)
				created.append(
					{
						"name": doc.name,
						"implementation": impl,
						"month": month_name,
						"total_hours": doc.total_hours,
						"billable_hours": doc.billable_hours,
					}
				)
			except Exception as e:
				frappe.db.rollback()
				errors.append(
					{"implementation": impl, "month": month_name, "error": str(e)}
				)

	frappe.db.commit()
	return {
		"naming_series": series,
		"created": created,
		"created_count": len(created),
		"skipped_count": len(skipped),
		"error_count": len(errors),
		"errors": errors[:10],
	}


def run():
	"""Seed Implementations, Projects, and Timesheets for MIS playground data."""
	frappe.set_user("Administrator")
	company = _pick_company()
	customer_group = _pick_customer_group()
	territory = _pick_territory()
	employees = _pick_employees()
	activity = _pick_activity_type()
	account_manager = _pick_account_manager()

	summary = {
		"company": company,
		"activity_type": activity,
		"account_manager": account_manager,
		"implementations": [],
		"timesheets_created": 0,
		"timesheets_skipped_existing": 0,
	}

	for spec in IMPL_SPECS:
		customer = _ensure_customer(spec["customer_name"], customer_group, territory)
		impl = _ensure_implementation(spec["impl_name"], customer, account_manager)
		project = _ensure_project(
			spec["project_name"], company, customer, impl, account_manager
		)

		impl_summary = {
			"implementation": impl,
			"customer": customer,
			"project": project,
			"months": {},
		}
		for month in MONTHS:
			result = _create_month_timesheets(
				spec,
				company=company,
				customer=customer,
				project=project,
				employees=employees,
				activity=activity,
				month=month,
			)
			impl_summary["months"][month] = {
				"created": result["created"],
				"skipped_existing": result["skipped_existing"],
			}
			summary["timesheets_created"] += result["created"]
			summary["timesheets_skipped_existing"] += result["skipped_existing"]

		summary["implementations"].append(impl_summary)

	frappe.db.commit()
	summary["mis"] = create_mis_records()
	return summary


if __name__ == "__main__":
	print(run())
