# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import cint, get_first_day, get_last_day, flt, getdate, add_to_date
from frappe.query_builder import DocType, Order
from frappe.desk.form.assign_to import add
from frappe.desk.form.assign_to import add as add_assignment

from phamos.phamos.doctype.implementation.implementation import (
	get_financial_history as get_implementation_financial_history,
)

MONTH_NAME_TO_NUM = {
	"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
	"July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
YEAR_MIN = 2000
YEAR_MAX = 2100


def _company_for_customer(customer):
	return (
		frappe.db.get_default("company")
		or frappe.db.get_value("Customer", customer, "customer_primary_company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
	)


def _so_hour_items(sales_order):
	if not sales_order:
		frappe.throw(frappe._("Sales Order is required."))
	items = frappe.get_all(
		"Sales Order Item",
		filters={"parent": sales_order},
		fields=["name", "item_code", "item_name", "description", "qty", "delivered_qty",
			"rate", "uom", "stock_uom", "conversion_factor"],
		order_by="idx asc",
	)
	if not items:
		frappe.throw(frappe._("Sales Order {0} has no items.").format(sales_order))
	hour_items = [
		i for i in items
		if (i.uom or "").strip() == "Hour" or (i.stock_uom or "").strip() == "Hour"
	]
	if hour_items:
		return hour_items
	if len(items) == 1:
		return items
	return []


def _get_month_date_range(year_str, month_name):
	if not year_str or not month_name:
		return None, None
	month_num = MONTH_NAME_TO_NUM.get(month_name)
	if not month_num:
		return None, None
	try:
		year_int = int(str(year_str).strip())
		first_day = get_first_day(f"{year_int}-{month_num:02d}-01")
		return first_day, get_last_day(first_day)
	except (ValueError, TypeError):
		return None, None


def _require_docname(docname):
	if not docname:
		raise frappe.ValidationError("docname is required")



def _so_row_qty_str(v):
	"""String for Sales Order Status Data fields — avoids 100 vs 100.0 after submit."""
	f = flt(v)
	return str(int(f)) if f == int(f) else ("%.6f" % f).rstrip("0").rstrip(".") or "0"


class MonthlyImplementationSummary(Document):

	def on_update(self):
		if not self.implementation:
			return

		account_manager = frappe.db.get_value(
			"Implementation",
			self.implementation,
			"account_manager"
		)

		if not account_manager:
			return

		# Remove existing assignments
		frappe.db.delete(
			"ToDo",
			{
				"reference_type": self.doctype,
				"reference_name": self.name,
				"status": ["!=", "Cancelled"],
			},
		)

		# Assign new account manager
		add_assignment({
			"assign_to": [account_manager],
			"doctype": self.doctype,
			"name": self.name,
		})
	def validate(self):
		prev = self.get_doc_before_save() if not self.is_new() else None
		if prev and self.docstatus == 0:
			period_changed = str(self.year or "").strip() != str(
				prev.year or ""
			).strip() or (self.month or "").strip() != (prev.month or "").strip()
			impl_changed = (self.implementation or "") != (prev.implementation or "")
			if period_changed or impl_changed:
				self.timesheets_table = []

		if cint(self.docstatus) == 0:
			self.status = "Draft"

		self.validate_year()
		self.validate_month()
		if self.implementation and self.year and self.month and not self.timesheets_table:
			self.set_timesheets_table()
		self._recalculate_totals_from_timesheets_table()
		self._recalculate_delivered_hours()
		self._sync_month_year_from_timesheet_dates()
		self.validate_year()
		self.validate_month()
		self.validate_duplicate_record()
		self._recalculate_delivery_note_item_amounts()
		if not self.is_closed():
			self._set_sales_order_status_information()
			self.populate_financial_history_fields()

	def is_closed(self):
		return cint(self.docstatus) == 1 and self.status == "Closed"

	def before_submit(self):
		self.status = "Open"
		self._auto_submit_draft_delivery_notes()
		self._recalculate_delivered_hours() 

	def _push_delivery_note_item_edits_to_draft_dns(self):
		by_dn = {}
		for row in self.delivery_note_item or []:
			if row.custom_ref_doc:
				by_dn.setdefault(row.custom_ref_doc, []).append(row)
		for dn_name, rows in by_dn.items():
			if cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or -1) != 0:
				continue
			dn = frappe.get_doc("Delivery Note", dn_name)
			changed = False
			for row in rows:
				target = next((it for it in dn.items if it.item_code == row.item_code), None)
				if not target:
					continue
				for fn in ("item_code", "description", "qty", "rate", "amount"):
					v = getattr(row, fn)
					if getattr(target, fn) != v:
						setattr(target, fn, v)
						changed = True
			if changed:
				dn.save()

	def _auto_submit_draft_delivery_notes(self):
		self._push_delivery_note_item_edits_to_draft_dns()
		errors = []
		prev_submitting = frappe.flags.get("mis_submitting")
		frappe.flags.mis_submitting = self.name
		try:
			for row in (self.mis_delivery_notes or []):
				dn_name = row.delivery_note
				if not dn_name or not frappe.db.exists("Delivery Note", dn_name):
					continue
				dn_status = cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
				if dn_status != 0:
					continue
				try:
					dn_doc = frappe.get_doc("Delivery Note", dn_name)
					dn_doc.submit()
					row.status = dn_doc.status or ""
					row.grand_total = flt(dn_doc.grand_total)
				except Exception as e:
					errors.append(f"{frappe.bold(dn_name)}: {str(e)}")
		finally:
			frappe.flags.mis_submitting = prev_submitting
		if errors:
			frappe.throw(
				frappe._("Could not submit the following Delivery Note(s):<br>{0}").format(
					"<br>".join(errors)
				)
			)

	def set_open_status(self, closed):
		if cint(self.docstatus) != 1:
			frappe.throw(frappe._("Only a submitted Monthly Implementation Summary can be closed or re-opened."))
		action = "Closed" if closed else "Re-opened"
		self._set_status("Closed" if closed else "Open", frappe._("{0} by {1}").format(action, frappe.session.user))

	def _set_status(self, status, comment):
		if self.status == status:
			return
		self.status = status
		self.flags.ignore_permissions = True
		self.flags.ignore_validate_update_after_submit = True
		if status == "Closed":
			self.flags.ignore_links = True  # child rows may reference already-cancelled DN/SI
		self.save()
		self.add_comment("Info", comment)

	def auto_close_if_fulfilled(self):
		if cint(self.docstatus) != 1 or self.status != "Open":
			return False
		if flt(self.billable_hours) > 0 and flt(self.delivered_hours) >= flt(self.billable_hours) - 0.0001:
			self._set_status("Closed", frappe._("Auto-closed: all billable hours have been delivered."))
			return True
		rows = self.sales_order_status_information or []
		if any((r.status or "") not in ("Completed", "Closed") for r in rows):
			return False
		sales_orders, delivery_notes = set(), set()
		for row in (self.mis_delivery_notes or []):
			if row.sales_order:
				sales_orders.add(row.sales_order)
			if row.delivery_note:
				delivery_notes.add(row.delivery_note)
		if not sales_orders and not delivery_notes and rows:
			return False
		for so in sales_orders:
			if frappe.db.get_value("Sales Order", so, "status") not in ("Completed", "Closed"):
				return False
		for dn in delivery_notes:
			if cint(frappe.db.get_value("Delivery Note", dn, "docstatus") or 0) == 2:
				continue
			if frappe.db.get_value("Delivery Note", dn, "status") not in ("Completed", "Closed"):
				return False
		self._set_status("Closed", frappe._("Auto-closed: all linked Sales Orders / Delivery Notes are fulfilled."))
		return True

	def _sync_snapshot(self):
		"""Fields sync_and_auto_close may touch — used to skip saving when nothing changed."""
		return (
			tuple((r.delivery_note, r.status, flt(r.grand_total)) for r in (self.mis_delivery_notes or [])),
			tuple((r.sales_invoice, r.status, flt(r.grand_total)) for r in (self.mis_sales_invoices or [])),
			tuple(
				(r.sales_order, r.status, r.total_hrs, r.delivered_total_hrs, r.remaining_hrs)
				for r in (self.sales_order_status_information or [])
			),
			(flt(self.sales_order_qty), flt(self.dn_qty), flt(self.timesheet_hrs), flt(self.remaining_hrs), cint(self.open_so)),
			(flt(self.delivered_hours), flt(self.remaining_billable_hours)),
		)

	def sync_and_auto_close(self):
		if self.is_closed():
			return False
		before = self._sync_snapshot()
		for row in (self.mis_delivery_notes or []):
			if not row.delivery_note:
				continue
			live = frappe.db.get_value("Delivery Note", row.delivery_note, ["status", "grand_total"], as_dict=True)
			if live and (row.status != (live.status or "") or flt(row.grand_total) != flt(live.grand_total)):
				row.status = live.status or ""
				row.grand_total = flt(live.grand_total)
		for row in (self.mis_sales_invoices or []):
			if not row.sales_invoice:
				continue
			live = frappe.db.get_value("Sales Invoice", row.sales_invoice, ["status", "grand_total"], as_dict=True)
			if live and (row.status != (live.status or "") or flt(row.grand_total) != flt(live.grand_total)):
				row.status = live.status or ""
				row.grand_total = flt(live.grand_total)
		if not self.is_closed():
			self._set_sales_order_status_information()
			self.populate_financial_history_fields()
			self._recalculate_delivered_hours()
		if self._sync_snapshot() != before:
			self.flags.ignore_permissions = True
			self.flags.ignore_validate_update_after_submit = True
			self.save()
		return self.auto_close_if_fulfilled()

	def _recalculate_delivery_note_item_amounts(self):
		for row in self.delivery_note_item or []:
			row.amount = flt(flt(row.qty) * flt(row.rate), row.precision("amount"))

	def populate_financial_history_fields(self):
		if not self.implementation:
			self._clear_financial_history_fields()
			return
		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			self._clear_financial_history_fields()
			return
		d = get_implementation_financial_history(self.implementation, customer) or {}
		self.sales_order_qty = flt(d.get("sales_order_qty"), 2)
		self.dn_qty = flt(d.get("dn_qty"), 2)
		self.timesheet_hrs = flt(d.get("timesheet_hrs"), 2)
		self.remaining_hrs = flt(d.get("remaining_hrs"), 2)
		self.open_so = 1 if d.get("open_so") else 0

	def _clear_financial_history_fields(self):
		self.sales_order_qty = self.dn_qty = self.timesheet_hrs = self.remaining_hrs = 0
		self.open_so = 0

	def _recalculate_delivered_hours(self):
		self.delivered_hours = flt(
			sum(
				flt(r.hours) for r in (self.mis_delivery_notes or [])
				if r.delivery_note and (r.status or "") not in ("Draft", "Cancelled")
			),
			2,
		)
		self.remaining_billable_hours = flt(flt(self.billable_hours) - self.delivered_hours, 2)

	def _set_sales_order_status_information(self):
		def clear_table():
			for r in list(self.sales_order_status_information or []):
				self.remove(r)

		if not self.implementation:
			clear_table()
			return
		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			clear_table()
			return

		so_filters = {
			"customer": customer,
			"custom_implementation": self.implementation,
			"docstatus": 1,
		}
		target = {}
		for o in frappe.get_all(
			"Sales Order",
			filters=so_filters,
			fields=["name", "status", "customer_name"],
			order_by="transaction_date desc",
		):
			hour_items = _so_hour_items(o.name)
			tot = flt(sum(flt(i.qty) for i in hour_items))
			deliv = flt(sum(flt(i.delivered_qty) for i in hour_items))
			rem = flt(tot - deliv, 2)
			target[o.name] = {
				"sales_order": o.name,
				"so_title": o.customer_name or "",
				"total_hrs": _so_row_qty_str(tot),
				"status": o.status or "",
				"delivered_total_hrs": _so_row_qty_str(deliv),
				"remaining_hrs": _so_row_qty_str(rem),
			}

		if cint(self.docstatus) == 1:
			seen = set()
			for row in list(self.sales_order_status_information or []):
				so = row.sales_order
				if so not in target:
					self.remove(row)
					continue
				t = target[so]
				seen.add(so)
				if (row.so_title or "") != (t["so_title"] or ""):
					row.so_title = t["so_title"]
				if (row.status or "") != (t["status"] or ""):
					row.status = t["status"]
				for fn in ("total_hrs", "delivered_total_hrs", "remaining_hrs"):
					if flt(getattr(row, fn)) != flt(t[fn]):
						setattr(row, fn, t[fn])
			for so, t in target.items():
				if so not in seen:
					self.append("sales_order_status_information", t)
			return

		self.sales_order_status_information = []
		for t in target.values():
			self.append("sales_order_status_information", t)

	def _create_dn_for_so_hours(self, sales_order, item_allocations, skip_default_stamp=False):
		if not item_allocations:
			frappe.throw(frappe._("No item hours given for Sales Order {0}.").format(sales_order))
		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			frappe.throw("Implementation has no Customer.")
		company = _company_for_customer(customer)
		if not company:
			frappe.throw("No Company found. Set default Company in Global Defaults.")
		dn_items = []
		total_hours = 0.0
		for alloc in item_allocations:
			so_line = frappe.get_doc("Sales Order Item", alloc["so_detail"])
			if so_line.parent != sales_order:
				frappe.throw(
					frappe._("Sales Order Item {0} does not belong to {1}.").format(alloc["so_detail"], sales_order)
				)
			hours = flt(alloc["hours"])
			rate = flt(so_line.rate)
			cf = flt(so_line.conversion_factor, 9) or 1
			dn_items.append({
				"item_code": so_line.item_code,
				"item_name": so_line.item_name,
				"description": so_line.description or "",
				"qty": hours,
				"uom": so_line.uom or so_line.stock_uom,
				"stock_uom": so_line.stock_uom or so_line.uom,
				"conversion_factor": cf,
				"rate": rate,
				"amount": flt(rate * hours, 2),
				"against_sales_order": sales_order,
				"so_detail": so_line.name,
				"allow_zero_valuation_rate": 1,
				"custom_against_monthly_implementation_summary": self.name,
			})
			total_hours += hours
		dn = frappe.get_doc({
			"doctype": "Delivery Note",
			"customer": customer,
			"company": company,
			"custom_implementation": self.implementation,
			"selling_price_list": frappe.db.get_value("Sales Order", sales_order, "selling_price_list"),
			"items": dn_items,
		})
		dn.insert()
		_add_or_update_mis_dn_row(self.name, dn.name, sales_order, total_hours)
		_mirror_dn_items_into_mis(self.name, dn.name)
		if not skip_default_stamp:
			self._stamp_timesheets_for_delivered_hours(dn.name, total_hours)
		return dn.name

	def _stamp_rows_in_window(self, dn_name, rows, start, end):
		"""Stamp custom_delivery_note on Timesheets in `rows` whose cumulative billable-hours slice overlaps [start, end)."""
		if not dn_name:
			return
		running = 0.0
		for row in rows:
			row_start, row_end = running, running + flt(row.billable_hours)
			running = row_end
			if row_end <= start or row_start >= end:
				continue
			ts = getattr(row, "timesheet", None)
			if not ts or not frappe.db.exists("Timesheet", ts):
				continue
			if frappe.db.get_value("Timesheet", ts, "custom_delivery_note"):
				continue
			frappe.db.set_value("Timesheet", ts, "custom_delivery_note", dn_name, update_modified=False)

	def _stamp_timesheets_for_delivered_hours(self, dn_name, hours):
		if not dn_name or flt(hours) <= 0 or not self.timesheets_table:
			return
		self._stamp_rows_in_window(
			dn_name, self.timesheets_table, flt(self.delivered_hours), flt(self.delivered_hours) + flt(hours)
		)

	def _sync_timesheet_delivery_note_column(self):
		ts_names = [r.timesheet for r in (self.timesheets_table or []) if r.timesheet]
		if not ts_names:
			return
		dn_by_ts = dict(frappe.get_all(
			"Timesheet",
			filters={"name": ["in", ts_names]},
			fields=["name", "custom_delivery_note"],
			as_list=True,
		))
		for row in self.timesheets_table or []:
			if row.timesheet and row.delivery_note != dn_by_ts.get(row.timesheet):
				row.delivery_note = dn_by_ts.get(row.timesheet)

	def validate_year(self):
		if not self.year:
			return
		year_str = (self.year or "").strip()
		if not year_str:
			frappe.throw("Year cannot be empty.")
		if len(year_str) != 4 or not year_str.isdigit():
			frappe.throw(f"Invalid year format. Use a 4-digit year (e.g. 2024). Got: {frappe.bold(self.year)}")
		try:
			y = int(year_str)
		except ValueError:
			frappe.throw(f"Invalid year format. Use a 4-digit year (e.g. 2024). Got: {frappe.bold(self.year)}")
		if y < YEAR_MIN or y > YEAR_MAX:
			frappe.throw(f"Year must be between {YEAR_MIN} and {YEAR_MAX}. Got: {frappe.bold(self.year)}")

	def validate_month(self):
		if self.month and self.month not in MONTH_NAME_TO_NUM:
			frappe.throw(
				f"Invalid month. Choose one of: January, February, March, April, May, June, "
				f"July, August, September, October, November, December. Got: {frappe.bold(self.month)}"
			)

	def validate_duplicate_record(self):
		if not (self.implementation and self.year and self.month):
			return
		# Only draft/submitted block duplicates; cancelled MIS can be replaced by a new doc.
		existing = frappe.get_all(
			"Monthly Implementation Summary",
			filters={
				"implementation": self.implementation,
				"year": self.year,
				"month": self.month,
				"name": ["!=", self.name],
				"docstatus": ["in", [0, 1]],
			},
			fields=["name"],
			limit=1,
		)
		if not existing:
			return
		link = frappe.utils.get_link_to_form("Monthly Implementation Summary", existing[0].name)
		impl = frappe.utils.get_link_to_form("Implementation", self.implementation)
		frappe.throw(
			f"A Monthly Implementation Summary record {link} already exists for "
			f"Implementation {impl}, Year {self.year} and Month {self.month}."
		)

	def _recalculate_totals_from_timesheets_table(self):
		if not self.timesheets_table:
			return
		self.total_hours = flt(sum(flt(r.total_hours) for r in self.timesheets_table), precision=2)
		self.billable_hours = flt(sum(flt(r.billable_hours) for r in self.timesheets_table), precision=2)

	def _sync_month_year_from_timesheet_dates(self):
		"""Keep Year / Month aligned with the calendar month of timesheet rows."""
		if not self.timesheets_table:
			return
		dates = []
		for r in self.timesheets_table:
			d = getattr(r, "date", None)
			if d:
				try:
					dates.append(getdate(d))
				except Exception:
					continue
		if not dates:
			return
		d0 = min(dates)
		months = list(MONTH_NAME_TO_NUM.keys())
		self.month = months[d0.month - 1]
		self.year = str(d0.year)

	def set_timesheets_table(self):
		if not self.year or not self.month:
			self.timesheets_table = []
			return
		from_date, to_date = _get_month_date_range(self.year, self.month)
		if not from_date or not to_date:
			self.timesheets_table = []
			return
		projects = frappe.get_all(
			"Project", filters={"custom_implementation": self.implementation}, pluck="name"
		)
		if not projects:
			self.timesheets_table = []
			return
		TS = DocType("Timesheet")
		TD = DocType("Timesheet Detail")
		Emp = DocType("Employee")
		rows = (
			frappe.qb.from_(TS)
			.inner_join(TD).on(TD.parent == TS.name)
			.inner_join(Emp).on(Emp.name == TS.employee)
			.select(
				TS.name.as_("ts_name"),
				TS.start_date.as_("date"),
				TS.total_hours,
				TS.total_billable_hours,
				TS.custom_rating.as_("rating"),
				TD.project.as_("project"),
				TS.employee,
				Emp.employee_name.as_("employee_name"),
				TS.note.as_("description"),
				TS.custom_delivery_note.as_("delivery_note"),
			)
			.where(TD.project.isin(projects))
			.where(TS.docstatus != 2)
			.where(TS.start_date.between(from_date, to_date))
			.orderby(Emp.employee_name, order=Order.asc)
			.orderby(TS.total_billable_hours, order=Order.desc)
		).run(as_dict=True)
		self.timesheets_table = []
		for row in rows:
			self.append(
				"timesheets_table",
				{
					"timesheet": row.ts_name or None,
					"date": row.date,
					"total_hours": flt(row.total_hours),
					"billable_hours": flt(row.total_billable_hours),
					"rating": row.rating or "",
					"project": row.project or None,
					"employee": row.employee or None,
					"employee_name": row.employee_name or "",
					"description": row.description or "",
					"delivery_note": row.delivery_note or None,
				},
			)


def _eligible_so_allocation_rows(doc):
	return [
		r for r in (doc.sales_order_status_information or [])
		if r.status in ("To Deliver", "To Deliver and Bill")
	]


def _parse_allocations(allocations):
	if isinstance(allocations, str):
		import json

		allocations = json.loads(allocations)
	out = []
	for a in allocations or []:
		so = (a.get("sales_order") or "").strip()
		if not so:
			continue
		items = [
			{"so_detail": (it.get("so_detail") or "").strip(), "hours": flt(it.get("hours"))}
			for it in (a.get("items") or [])
			if (it.get("so_detail") or "").strip() and flt(it.get("hours")) > 0
		]
		if items:
			out.append({"sales_order": so, "items": items})
	return out


def _existing_draft_dn_hours(doc):
	"""Sum of hours already sitting in draft Delivery Notes for this MIS, keyed by Sales Order."""
	totals = {}
	for r in doc.mis_delivery_notes or []:
		if r.status == "Draft" and r.sales_order:
			totals[r.sales_order] = flt(totals.get(r.sales_order, 0)) + flt(r.hours)
	return totals


def _build_dn_allocation_rows(doc, pool, wanted=None):
	existing_draft_hours = _existing_draft_dn_hours(doc)
	rows = []
	for r in _eligible_so_allocation_rows(doc):
		if wanted is not None and r.sales_order not in wanted:
			continue
		item_rows = []
		for i in _so_hour_items(r.sales_order):
			remaining = flt(flt(i.qty) - flt(i.delivered_qty), 2)
			if remaining <= 0.0001:
				continue
			alloc = flt(min(remaining, pool), 2) if pool > 0 else 0
			pool = flt(pool - alloc, 2)
			item_rows.append({
				"so_detail": i.name,
				"item_code": i.item_code,
				"item_name": i.item_name,
				"remaining_qty": remaining,
				"allocated_hours": alloc,
			})
		if not item_rows:
			continue
		rows.append({
			"sales_order": r.sales_order,
			"items": item_rows,
			"so_remaining_hrs": flt(sum(it["remaining_qty"] for it in item_rows), 2),
			"existing_draft_hours": flt(existing_draft_hours.get(r.sales_order, 0)),
		})
	return rows


@frappe.whitelist()
def get_dn_allocation_preview(docname: str, sales_orders=None):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	wanted = set(_parse_timesheet_names(sales_orders)) if sales_orders else None
	rows = _build_dn_allocation_rows(doc, flt(doc.remaining_billable_hours), wanted)
	return {"rows": rows, "remaining_billable_hours": flt(doc.remaining_billable_hours)}


@frappe.whitelist()
def get_dn_allocation_preview_for_timesheets(docname: str, timesheets):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	ts_names = set(_parse_timesheet_names(timesheets))
	selected_hours = flt(
		sum(flt(r.billable_hours) for r in (doc.timesheets_table or []) if r.timesheet in ts_names), 2
	)
	rows = _build_dn_allocation_rows(doc, selected_hours)
	return {
		"rows": rows,
		"remaining_billable_hours": flt(doc.remaining_billable_hours),
		"selected_hours": selected_hours,
	}


def _create_dns_for_allocations(doc, allocations, pool, stamp_fn=None):
	"""Shared by create_dns_from_allocations and create_dns_from_timesheet_allocations.

	stamp_fn(dn_name, hours), if given, replaces the default whole-table windowed timesheet stamping.
	"""
	eligible_so = {r.sales_order for r in _eligible_so_allocation_rows(doc)}
	created = []
	for a in _parse_allocations(allocations):
		so = a["sales_order"]
		if so not in eligible_so:
			frappe.throw(frappe._("Sales Order {0} is not eligible for delivery.").format(so))
		item_remaining = {i.name: flt(i.qty) - flt(i.delivered_qty) for i in _so_hour_items(so)}
		so_items, so_total = [], 0.0
		for it in a["items"]:
			so_detail, hours = it["so_detail"], flt(it["hours"], 2)
			if so_detail not in item_remaining:
				frappe.throw(frappe._("Sales Order Item {0} is not eligible for delivery.").format(so_detail))
			if hours > item_remaining[so_detail] + 0.0001:
				frappe.throw(
					frappe._("Hours for item {0} exceed its remaining hours ({1}).").format(
						so_detail, item_remaining[so_detail]
					)
				)
			so_items.append({"so_detail": so_detail, "hours": hours})
			so_total += hours
		if not so_items:
			continue
		if so_total > pool + 0.0001:
			frappe.throw(frappe._("Hours for {0} exceed the remaining billable hours ({1}).").format(so, pool))
		dn_name = doc._create_dn_for_so_hours(so, so_items, skip_default_stamp=bool(stamp_fn))
		if stamp_fn:
			stamp_fn(dn_name, so_total)
		created.append(dn_name)
		doc.delivered_hours = flt(doc.delivered_hours) + so_total
		pool = flt(pool - so_total, 2)
	return created


def _save_after_dn_creation(doc):
	doc.reload()
	doc._recalculate_delivered_hours()
	doc._sync_timesheet_delivery_note_column()
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()


@frappe.whitelist()
def create_dns_from_allocations(docname: str, allocations):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	if doc.status == "Closed":
		frappe.throw(frappe._("This Monthly Implementation Summary is closed."))

	created = _create_dns_for_allocations(doc, allocations, flt(doc.remaining_billable_hours))
	if created:
		_save_after_dn_creation(doc)
	return {"status": "ok", "created": created}


@frappe.whitelist()
def create_dns_from_timesheet_allocations(docname: str, timesheets, allocations):
	"""Same allocation flow as create_dns_from_allocations, but the pool is the selected Timesheets'
	own billable hours, and only those Timesheets are stamped with the created Delivery Note(s)."""
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	if doc.status == "Closed":
		frappe.throw(frappe._("This Monthly Implementation Summary is closed."))

	ts_names = set(_parse_timesheet_names(timesheets))
	selected_rows = [r for r in (doc.timesheets_table or []) if r.timesheet in ts_names]
	if not selected_rows:
		frappe.throw(frappe._("No Timesheets selected."))
	pool = flt(sum(flt(r.billable_hours) for r in selected_rows), 2)

	cursor = {"pos": 0.0}

	def stamp(dn_name, hours):
		doc._stamp_rows_in_window(dn_name, selected_rows, cursor["pos"], cursor["pos"] + hours)
		cursor["pos"] += hours

	created = _create_dns_for_allocations(doc, allocations, pool, stamp_fn=stamp)
	if created:
		_save_after_dn_creation(doc)
	return {"status": "ok", "created": created}


def _add_or_update_mis_dn_row(docname, dn_name, sales_order=None, hours=None):
	if not docname or not dn_name:
		return
	dn_doc = frappe.get_doc("Delivery Note", dn_name)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.reload()
	existing = next(
		(r for r in (doc.mis_delivery_notes or []) if r.delivery_note == dn_name),
		None,
	)
	data = {
		"delivery_note": dn_name,
		"sales_order": sales_order,
		"status": dn_doc.status or "",
		"grand_total": flt(dn_doc.grand_total),
		"posting_date": dn_doc.posting_date,
	}
	if hours is not None:
		data["hours"] = flt(hours, 2)
	if existing:
		for k, v in data.items():
			setattr(existing, k, v)
	else:
		doc.append("mis_delivery_notes", data)
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()


@frappe.whitelist()
def set_mis_open_status(docname: str, closed):
	_require_docname(docname)
	frappe.has_permission("Monthly Implementation Summary", "submit", docname, throw=True)
	frappe.get_doc("Monthly Implementation Summary", docname).set_open_status(cint(closed))
	return {"status": "ok"}



def _submit_docs_in_mis(docname, names, doctype, child_table, child_fieldname):
	"""Shared body for submit_delivery_notes_in_mis / submit_sales_invoices_in_mis."""
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("write")

	target_names = _parse_timesheet_names(names)
	if not target_names:
		return {"submitted": 0, "already_submitted": 0, "failed": 0, "failed_details": []}

	allowed = {(row.get(child_fieldname) or "") for row in (doc.get(child_table) or []) if row.get(child_fieldname)}

	submitted = 0
	already_submitted = 0
	failed_details = []

	for name in target_names:
		if name not in allowed:
			failed_details.append({child_fieldname: name, "error": "Not part of this MIS."})
			continue
		if not frappe.db.exists(doctype, name):
			failed_details.append({child_fieldname: name, "error": f"{doctype} not found."})
			continue
		docstatus = cint(frappe.db.get_value(doctype, name, "docstatus") or 0)
		if docstatus == 2:
			failed_details.append({child_fieldname: name, "error": f"{doctype} is cancelled."})
			continue
		if docstatus == 1:
			already_submitted += 1
			continue
		try:
			target_doc = frappe.get_doc(doctype, name)
			target_doc.check_permission("submit")
			target_doc.submit()
			for row in (doc.get(child_table) or []):
				if row.get(child_fieldname) == name:
					frappe.db.set_value(
						row.doctype, row.name,
						{"status": target_doc.status or "", "grand_total": flt(target_doc.grand_total)},
						update_modified=False,
					)
					break
			submitted += 1
		except Exception as e:
			failed_details.append({child_fieldname: name, "error": str(e)})

	return {
		"submitted": submitted,
		"already_submitted": already_submitted,
		"failed": len(failed_details),
		"failed_details": failed_details,
	}


@frappe.whitelist()
def submit_delivery_notes_in_mis(docname: str, delivery_notes):
	return _submit_docs_in_mis(docname, delivery_notes, "Delivery Note", "mis_delivery_notes", "delivery_note")


@frappe.whitelist()
def submit_sales_invoices_in_mis(docname: str, sales_invoices):
	return _submit_docs_in_mis(docname, sales_invoices, "Sales Invoice", "mis_sales_invoices", "sales_invoice")


def _find_existing_sales_invoice_for_delivery_note(delivery_note):
	if not delivery_note:
		return None

	row = frappe.db.sql(
		"""
		select distinct si.name
		from `tabSales Invoice` si
		inner join `tabSales Invoice Item` sii on sii.parent = si.name
		where si.docstatus != 2
			and (
				sii.delivery_note = %(delivery_note)s
				or sii.dn_detail in (
					select dni.name
					from `tabDelivery Note Item` dni
					where dni.parent = %(delivery_note)s
				)
			)
		order by si.creation desc
		limit 1
		""",
		{"delivery_note": delivery_note},
		as_dict=True,
	)
	if row:
		return row[0].name

	if frappe.db.has_column("Sales Invoice", "against_delivery_note"):
		si = frappe.db.get_value(
			"Sales Invoice",
			{"against_delivery_note": delivery_note, "docstatus": ["!=", 2]},
			"name",
		)
		if si:
			return si

	return None


def _timesheet_is_pending_for_approval(docstatus, status=None):
	status_norm = (status or "").strip().lower()
	if status_norm:
		return status_norm == "draft"

	if cint(docstatus) == 2:
		return False
	if cint(docstatus) == 1:
		return False
	return True


def _parse_timesheet_names(timesheets):
	if not timesheets:
		return []
	if isinstance(timesheets, str):
		try:
			import json

			timesheets = json.loads(timesheets)
		except Exception:
			timesheets = [timesheets]
	if not isinstance(timesheets, (list, tuple, set)):
		return []
	out = []
	seen = set()
	for ts in timesheets:
		name = (str(ts or "")).strip()
		if not name or name in seen:
			continue
		seen.add(name)
		out.append(name)
	return out


def _parse_timesheet_billable_rows(rows):
	if not rows:
		return []
	if isinstance(rows, str):
		try:
			import json

			rows = json.loads(rows)
		except Exception:
			return []
	if not isinstance(rows, (list, tuple)):
		return []
	out = []
	for row in rows:
		if not isinstance(row, dict):
			continue
		ts_name = (str(row.get("timesheet") or "")).strip()
		if not ts_name:
			continue
		out.append({"timesheet": ts_name, "billable_hours": flt(row.get("billable_hours"))})
	return out


def _set_timesheet_billable_hours(ts_doc, target_billable_hours):
	if cint(ts_doc.docstatus) != 0:
		frappe.throw(frappe._("Timesheet {0} is not in Draft.").format(frappe.bold(ts_doc.name)))

	logs = list(ts_doc.get("time_logs") or [])
	if not logs:
		frappe.throw(frappe._("Timesheet {0} has no time logs.").format(frappe.bold(ts_doc.name)))

	target = max(flt(target_billable_hours), 0)
	total_hours = flt(sum(flt(getattr(log, "hours", 0)) for log in logs), 2)

	if target > total_hours:
		frappe.throw(
			frappe._(
				"Billable hours ({0}) cannot exceed total hours ({1}) on {2}."
			).format(frappe.bold(target), frappe.bold(total_hours), frappe.bold(ts_doc.name))
		)

	if total_hours <= 0:
		for idx, log in enumerate(logs):
			bill = target if idx == 0 else 0
			log.billing_hours = bill
		ts_doc.save(ignore_permissions=True)
		ts_doc.reload()
		total_billable_hours = flt(sum(flt(getattr(log, "billing_hours", 0)) for log in (ts_doc.time_logs or [])), 2)
		frappe.db.set_value(
			"Timesheet",
			ts_doc.name,
			{"total_billable_hours": total_billable_hours},
			update_modified=False,
		)
		return

	running = 0.0
	for idx, log in enumerate(logs):
		if idx == len(logs) - 1:
			bill = flt(target - running, 2)
		else:
			ratio = flt(getattr(log, "hours", 0)) / total_hours if total_hours else 0
			bill = flt(target * ratio, 2)
			running += bill
		bill = max(bill, 0)
		log.billing_hours = bill

	ts_doc.save(ignore_permissions=True)
	ts_doc.reload()
	total_billable_hours = flt(sum(flt(getattr(log, "billing_hours", 0)) for log in (ts_doc.time_logs or [])), 2)
	frappe.db.set_value(
		"Timesheet",
		ts_doc.name,
		{"total_billable_hours": total_billable_hours},
		update_modified=False,
	)


@frappe.whitelist()
def get_timesheet_approval_rows(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")

	base_rows = list(doc.timesheets_table or [])
	timesheet_names = [
		(str(getattr(r, "timesheet", "") or "").strip())
		for r in base_rows
		if (str(getattr(r, "timesheet", "") or "").strip())
	]
	meta_by_name = {}
	if timesheet_names:
		ts_has_status = frappe.db.has_column("Timesheet", "status")
		ts_fields = ["name", "docstatus"]
		if ts_has_status:
			ts_fields.append("status")
		for ts in frappe.get_all(
			"Timesheet",
			filters={"name": ["in", list(set(timesheet_names))]},
			fields=ts_fields,
		):
			meta_by_name[ts.name] = ts

	result = []
	for row in base_rows:
		ts_name = (getattr(row, "timesheet", "") or "").strip()
		emp_name = (getattr(row, "employee_name", "") or "").strip()
		row_project = (getattr(row, "project", "") or "").strip()
		row_employee = (getattr(row, "employee", "") or "").strip()
		meta = meta_by_name.get(ts_name)
		docstatus = cint(meta.docstatus) if meta else 0
		status = (meta.status if meta else "") or ""
		is_pending = _timesheet_is_pending_for_approval(docstatus, status)

		if not is_pending:
			continue

		result.append(
			{
				"timesheet": ts_name,
				"date": str(getattr(row, "date", "") or ""),
				"employee_name": emp_name,
				"employee": row_employee,
				"project": row_project,
				"total_hours": flt(getattr(row, "total_hours", 0)),
				"billable_hours": flt(getattr(row, "billable_hours", 0)),
				"description": (getattr(row, "description", "") or ""),
				"rating": (getattr(row, "rating", "") or ""),
				"delivery_note": (getattr(row, "delivery_note", "") or ""),
				"docstatus": docstatus,
				"status": status,
				"is_pending": 1 if is_pending else 0,
			}
		)

	return result


@frappe.whitelist()
def save_timesheet_billable_in_mis(docname: str, rows):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")

	updates = _parse_timesheet_billable_rows(rows)
	if not updates:
		return {"updated": 0, "failed": 0, "failed_details": []}

	allowed = {
		(str(getattr(r, "timesheet", "") or "")).strip()
		for r in (doc.timesheets_table or [])
		if (str(getattr(r, "timesheet", "") or "")).strip()
	}

	updated = 0
	updated_timesheets = []
	failed_details = []

	for row in updates:
		ts_name = row["timesheet"]
		if ts_name not in allowed:
			failed_details.append({"timesheet": ts_name, "error": "Timesheet is not part of this MIS."})
			continue
		if not frappe.db.exists("Timesheet", ts_name):
			failed_details.append({"timesheet": ts_name, "error": "Timesheet not found."})
			continue

		try:
			ts_doc = frappe.get_doc("Timesheet", ts_name)
			# MIS action should be able to persist draft-hour corrections for linked timesheets.
			_set_timesheet_billable_hours(ts_doc, row["billable_hours"])
			updated += 1
			updated_timesheets.append(ts_name)
		except Exception as e:
			failed_details.append({"timesheet": ts_name, "error": str(e)})

	if updated:
		doc.reload()
		doc.set_timesheets_table()
		doc._recalculate_totals_from_timesheets_table()
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()
		frappe.db.commit()

	return {
		"updated": updated,
		"updated_timesheets": updated_timesheets,
		"requested": len(updates),
		"failed": len(failed_details),
		"failed_details": failed_details,
	}


@frappe.whitelist()
def approve_timesheets_in_mis(docname: str, timesheets):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")

	selected = _parse_timesheet_names(timesheets)
	if not selected:
		return {"approved": 0, "already_approved": 0, "failed": 0, "failed_details": []}

	allowed = {
		(str(getattr(r, "timesheet", "") or "")).strip()
		for r in (doc.timesheets_table or [])
		if (str(getattr(r, "timesheet", "") or "")).strip()
	}

	approved = 0
	already_approved = 0
	failed_details = []

	for ts_name in selected:
		if ts_name not in allowed:
			failed_details.append({"timesheet": ts_name, "error": "Timesheet is not part of this MIS."})
			continue
		if not frappe.db.exists("Timesheet", ts_name):
			failed_details.append({"timesheet": ts_name, "error": "Timesheet not found."})
			continue

		try:
			ts_doc = frappe.get_doc("Timesheet", ts_name)
			ts_doc.check_permission("submit")
			if not _timesheet_is_pending_for_approval(
				ts_doc.docstatus,
				getattr(ts_doc, "status", None),
			):
				already_approved += 1
				continue

			if cint(ts_doc.docstatus) == 0:
				ts_doc.submit()

			approved += 1
		except Exception as e:
			failed_details.append({"timesheet": ts_name, "error": str(e)})

	return {
		"approved": approved,
		"already_approved": already_approved,
		"failed": len(failed_details),
		"failed_details": failed_details,
	}


@frappe.whitelist()
def create_sales_invoice_from_mis(docname: str, delivery_note: str = None):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")
	if doc.status == "Closed":
		frappe.throw(frappe._("This Monthly Implementation Summary is closed."))

	if not delivery_note:
		frappe.throw(frappe._("Delivery Note is required to create a Sales Invoice."))

	delivery_note = delivery_note.strip()

	if not frappe.db.exists("Delivery Note", delivery_note):
		frappe.throw(frappe._("Delivery Note {0} does not exist.").format(frappe.bold(delivery_note)))

	dn_docstatus = cint(frappe.db.get_value("Delivery Note", delivery_note, "docstatus") or 0)
	if dn_docstatus == 2:
		frappe.throw(frappe._("Delivery Note {0} is cancelled.").format(frappe.bold(delivery_note)))
	if dn_docstatus != 1:
		frappe.throw(
			frappe._("Delivery Note {0} must be submitted before creating a Sales Invoice.").format(
				frappe.bold(delivery_note)
			)
		)

	if not frappe.has_permission("Sales Invoice", "create"):
		raise frappe.PermissionError

	existing_si = _find_existing_sales_invoice_for_delivery_note(delivery_note)
	if existing_si:
		existing_si_docstatus = cint(frappe.db.get_value("Sales Invoice", existing_si, "docstatus") or 0)
		if existing_si_docstatus == 0:
			# Draft SI exists — link it to MIS and return it
			si_doc = frappe.get_doc("Sales Invoice", existing_si)
			doc.reload()
			dn_sales_order = None
			for row in (doc.mis_delivery_notes or []):
				if row.delivery_note == delivery_note:
					dn_sales_order = row.sales_order
					break
			doc.reload()
			existing_si_row = next(
				(r for r in (doc.mis_sales_invoices or []) if r.sales_invoice == existing_si),
				None,
			)
			if not existing_si_row:
				doc.append("mis_sales_invoices", {
					"sales_invoice": existing_si,
					"delivery_note": delivery_note,
					"sales_order": dn_sales_order,
					"status": si_doc.status or "",
					"grand_total": flt(si_doc.grand_total),
					"posting_date": si_doc.posting_date,
				})
				doc.flags.ignore_permissions = True
				doc.flags.ignore_validate_update_after_submit = True
				doc.save()
			return {"status": "ok", "sales_invoice": existing_si}
		si_link = frappe.utils.get_link_to_form("Sales Invoice", existing_si)
		frappe.throw(
			frappe._("A Sales Invoice {0} already exists for Delivery Note {1}.").format(
				si_link, frappe.bold(delivery_note)
			)
		)

	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

	si_doc = make_sales_invoice(delivery_note)
	if not si_doc or not getattr(si_doc, "items", None):
		frappe.throw(
			frappe._("No billable items available to create Sales Invoice from Delivery Note {0}.").format(
				frappe.bold(delivery_note)
			)
		)

	si_doc.insert()

	# Add a mis_sales_invoices row referencing the delivery note and its sales order
	doc.reload()
	dn_sales_order = None
	for row in (doc.mis_delivery_notes or []):
		if row.delivery_note == delivery_note:
			dn_sales_order = row.sales_order
			break
	existing_si_row = next(
		(r for r in (doc.mis_sales_invoices or []) if r.sales_invoice == si_doc.name),
		None,
	)
	if not existing_si_row:
		doc.append("mis_sales_invoices", {
			"sales_invoice": si_doc.name,
			"delivery_note": delivery_note,
			"sales_order": dn_sales_order,
			"status": si_doc.status or "",
			"grand_total": flt(si_doc.grand_total),
			"posting_date": si_doc.posting_date,
		})
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()

	return {"status": "ok", "sales_invoice": si_doc.name}


def _mirror_dn_items_into_mis(docname, dn_name):
	"""Mirror a linked Delivery Note's line items into delivery_note_item for display/audit —
	replaces any rows previously mirrored from the same DN."""
	if not docname or not dn_name:
		return
	dn_doc = frappe.get_doc("Delivery Note", dn_name)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.reload()
	doc.delivery_note_item = [r for r in (doc.delivery_note_item or []) if r.custom_ref_doc != dn_name]
	for item in dn_doc.items:
		doc.append("delivery_note_item", {
			"item_code": item.item_code,
			"item_name": item.item_name,
			"description": item.description,
			"item_group": item.item_group,
			"qty": item.qty,
			"stock_uom": item.stock_uom,
			"uom": item.uom,
			"conversion_factor": item.conversion_factor,
			"rate": item.rate,
			"amount": item.amount,
			"expense_account": item.expense_account,
			"cost_center": item.cost_center,
			"custom_ref_doc": dn_name,
		})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_validate_update_after_submit = True
	doc.save()


def _open_mis_for_implementations(implementations):
	"""Draft/submitted MIS for any of the given Implementations — used to catch Sales Order /
	Delivery Note / Sales Invoice changes made entirely outside the MIS UI."""
	names = set()
	for impl in implementations:
		if not impl:
			continue
		names.update(frappe.get_all(
			"Monthly Implementation Summary",
			filters={"implementation": impl, "docstatus": ["in", [0, 1]]},
			pluck="name",
		))
	return names


def _implementations_for_delivery_note(dn):
	impl = {getattr(dn, "custom_implementation", None)}
	for item in dn.get("items") or []:
		so = getattr(item, "against_sales_order", None)
		if so:
			impl.add(frappe.db.get_value("Sales Order", so, "custom_implementation"))
	impl.discard(None)
	return impl


def _implementations_for_sales_invoice(si):
	impl = set()
	for item in si.get("items") or []:
		so = getattr(item, "sales_order", None)
		dn = getattr(item, "delivery_note", None)
		if so:
			impl.add(frappe.db.get_value("Sales Order", so, "custom_implementation"))
		if dn:
			impl.add(frappe.db.get_value("Delivery Note", dn, "custom_implementation"))
	impl.discard(None)
	return impl


def _mis_after_dn_submit(dn):
	"""(mis_names_get_timesheet_stamp, mis_names_to_save) for this submitted Delivery Note."""
	stamp = set()
	for n in frappe.get_all("MIS Delivery Note", filters={"delivery_note": dn.name}, pluck="parent"):
		if n and cint(frappe.db.get_value("Monthly Implementation Summary", n, "docstatus")) != 2:
			stamp.add(n)
	for n in frappe.get_all(
		"Delivery Note Item",
		filters={"parent": dn.name, "custom_against_monthly_implementation_summary": ["is", "set"]},
		pluck="custom_against_monthly_implementation_summary",
	):
		if n:
			stamp.add(n)
	for n in frappe.get_all(
		"Delivery Note Item",
		filters={"parenttype": "Monthly Implementation Summary", "custom_ref_doc": dn.name},
		pluck="parent",
		distinct=True,
	):
		if n and cint(frappe.db.get_value("Monthly Implementation Summary", n, "docstatus")) != 2:
			stamp.add(n)

	save = set(stamp)
	save.update(_open_mis_for_implementations(_implementations_for_delivery_note(dn)))
	return stamp, save


def update_mis_timesheets_on_delivery_note_submit(doc, method=None):
	if not doc or getattr(doc, "doctype", None) != "Delivery Note" or cint(doc.docstatus) != 1:
		return
	stamp, save = _mis_after_dn_submit(doc)
	dn_name = doc.name
	submitting = frappe.flags.get("mis_submitting")
	for mis_name in save:
		if mis_name == submitting:
			continue
		if not mis_name or not frappe.db.exists("Monthly Implementation Summary", mis_name):
			continue
		m = frappe.get_doc("Monthly Implementation Summary", mis_name)
		if m.is_closed():
			continue
		if mis_name in stamp:
			_mirror_dn_items_into_mis(mis_name, dn_name)
			m.reload()  # mirror wrote delivery_note_item via a separate doc instance — pick it back up
			m._sync_timesheet_delivery_note_column()  # windowed per-DN stamps, not a blanket overwrite
			m.flags.ignore_permissions = True
			m.flags.ignore_validate_update_after_submit = True
			m.save()
		try:
			m.sync_and_auto_close()
		except Exception:
			frappe.log_error(title="MIS refresh after Delivery Note submit", message=frappe.get_traceback())


def _sync_and_auto_close_mis(mis_names):
	for mis_name in mis_names:
		if not mis_name or not frappe.db.exists("Monthly Implementation Summary", mis_name):
			continue
		try:
			frappe.get_doc("Monthly Implementation Summary", mis_name).sync_and_auto_close()
		except Exception:
			frappe.log_error(title="MIS status resync", message=frappe.get_traceback())


def auto_close_fulfilled_mis():
	"""Scheduled fallback: Sales Order / Delivery Note / Sales Invoice status changes don't always
	trigger doc hooks, so periodically re-sync open MIS directly against live status."""
	open_names = frappe.get_all(
		"Monthly Implementation Summary",
		filters={"docstatus": 1, "status": "Open"},
		pluck="name",
	)
	_sync_and_auto_close_mis(open_names)


def sync_mis_status_for_source_doc(doc, method=None):
	if doc.doctype == "Delivery Note":
		mis_names = set(frappe.get_all("MIS Delivery Note", filters={"delivery_note": doc.name}, pluck="parent"))
		mis_names.update(_open_mis_for_implementations(_implementations_for_delivery_note(doc)))
	elif doc.doctype == "Sales Invoice":
		mis_names = set(frappe.get_all("MIS Sales Invoice", filters={"sales_invoice": doc.name}, pluck="parent"))
		mis_names.update(_open_mis_for_implementations(_implementations_for_sales_invoice(doc)))
	else:
		mis_names = _open_mis_for_implementations([getattr(doc, "custom_implementation", None)])
	_sync_and_auto_close_mis(mis_names)
