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


def _rate_from_dn_line(itm):
	r = flt(itm.rate)
	if r > 0:
		return r
	q = flt(itm.qty)
	if q and flt(itm.amount):
		return flt(flt(itm.amount) / q)
	return 0


def _rate_from_so_detail(so_detail_name):
	if not so_detail_name or not frappe.db.exists("Sales Order Item", so_detail_name):
		return 0
	return flt(frappe.db.get_value("Sales Order Item", so_detail_name, "rate"))


def _rate_from_sales_order(so_name, item_code):
	if not so_name or not item_code:
		return 0
	for row in frappe.get_doc("Sales Order", so_name).items:
		if row.item_code == item_code:
			r = flt(row.rate)
			if r > 0:
				return r
	return 0


def _resolve_rate_for_mis_from_dn_row(mis_doc, dn_item):
	"""Create-DN sync: DN / SO only, never Item Price."""
	r = _rate_from_dn_line(dn_item)
	if not r and getattr(dn_item, "so_detail", None):
		r = _rate_from_so_detail(dn_item.so_detail)
	if not r and mis_doc.sales_order:
		r = _rate_from_sales_order(mis_doc.sales_order, dn_item.item_code)
	return flt(r, 2)


def _so_line_for_billable_hours(sales_order):
	"""SO line when creating a Delivery Note from billable hours: open lines first, prefer Hour UOM."""
	if not sales_order:
		frappe.throw(frappe._("Sales Order is required."))
	so = frappe.get_doc("Sales Order", sales_order)
	if not so.items:
		frappe.throw(frappe._("Sales Order {0} has no items.").format(sales_order))
	open_lines = [
		d
		for d in so.items
		if abs(flt(d.delivered_qty)) < abs(flt(d.qty)) and not getattr(d, "delivered_by_supplier", 0)
	]
	pool = open_lines if open_lines else list(so.items)
	hour_lines = [
		d
		for d in pool
		if (getattr(d, "uom", None) or "").strip() == "Hour"
		or (getattr(d, "stock_uom", None) or "").strip() == "Hour"
	]
	if hour_lines:
		return hour_lines[0]
	if len(pool) == 1:
		return pool[0]
	return pool[0]


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


def _delivered_hours_against_sales_order(sales_order_name):
	"""Submitted DN line qty linked to SO — same logic as Implementation.add_delivered_hrs."""
	rows = frappe.db.sql(
		"""
		SELECT dni.qty
		FROM `tabDelivery Note Item` dni
		INNER JOIN `tabDelivery Note` dn ON dn.name = dni.parent
		WHERE dni.against_sales_order = %s
			AND dn.docstatus = 1
			AND IFNULL(dn.status, '') NOT IN ('Cancelled', 'Closed')
		""",
		sales_order_name,
		as_dict=True,
	)
	return flt(sum(flt(r.get("qty")) for r in rows)) if rows else 0


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

		self.validate_year()
		self.validate_month()
		if self.implementation and self.year and self.month and not self.timesheets_table:
			self.set_timesheets_table()
		self._recalculate_totals_from_timesheets_table()
		self._sync_month_year_from_timesheet_dates()
		self.validate_year()
		self.validate_month()
		self.validate_duplicate_record()
		self._recalculate_delivery_note_item_amounts()
		self._set_sales_order_status_information()
		self.populate_financial_history_fields()

	def before_submit(self):
		self._sync_delivery_note_from_mis_items_for_submit()
		self._submit_linked_delivery_note_before_mis_submit()

	def on_submit(self):
		dn_name = self._resolve_dn_name_for_timesheet_stamp()
		if dn_name:
			self._update_timesheets_delivery_note(dn_name)

	def _submit_linked_delivery_note_before_mis_submit(self):
		dn_name = (self.delivery_note or "").strip()
		if not dn_name:
			dn_name = self._get_linked_dn_name(persist_link=True)

		if not dn_name:
			frappe.throw(frappe._("No Delivery Note linked to this Monthly Implementation Summary."))

		if not frappe.db.exists("Delivery Note", dn_name):
			frappe.throw(frappe._("Delivery Note {0} does not exist.").format(frappe.bold(dn_name)))

		dn = frappe.get_doc("Delivery Note", dn_name)
		dn_status = cint(dn.docstatus)

		if dn_status == 2:
			frappe.throw(frappe._("Delivery Note {0} is cancelled.").format(frappe.bold(dn_name)))

		self.delivery_note = dn.name

	def _resolve_dn_name_for_timesheet_stamp(self):
		"""Resolve Delivery Note for stamping timesheets: DB ``delivery_note`` first (reliable after
		workflow / ``db_set``), then latest non-cancelled DN whose item row links this MIS, then
		``_get_linked_dn_name`` fallbacks (SO / implementation).
		"""
		if not self.name:
			return None
		dn = frappe.db.get_value(self.doctype, self.name, "delivery_note")
		if dn and frappe.db.exists("Delivery Note", dn):
			ds = frappe.db.get_value("Delivery Note", dn, "docstatus")
			if ds is not None and int(ds) != 2:
				return dn
		row = frappe.db.sql(
			"""
			select dni.parent
			from `tabDelivery Note Item` dni
			inner join `tabDelivery Note` dn on dn.name = dni.parent
			where ifnull(dn.docstatus, 0) != 2
				and dni.custom_against_monthly_implementation_summary = %s
			order by dni.modified desc
			limit 1
			""",
			self.name,
			as_list=True,
		)
		if row and row[0] and row[0][0]:
			return row[0][0]
		return self._get_linked_dn_name(persist_link=False)

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

	def _refresh_sales_order_status_and_financials(self):
		self._set_sales_order_status_information()
		self.populate_financial_history_fields()

	def _set_sales_order_status_information(self):
		# Open SOs for this implementation + delivered hrs (like Implementation). Submitted: update rows in place
		# so child row names stay valid; draft: rebuild table.
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

		open_so = {
			"customer": customer,
			"custom_implementation": self.implementation,
			"status": ["in", ["To Deliver", "To Bill", "To Deliver and Bill"]],
			"docstatus": 1,
		}
		target = {}
		for o in frappe.get_all(
			"Sales Order",
			filters=open_so,
			fields=["name", "status", "total_qty", "customer_name"],
			order_by="transaction_date desc",
		):
			tot, deliv = flt(o.total_qty), _delivered_hours_against_sales_order(o.name)
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

	def validate_timesheet_hours_for_delivery_note(self):
		if flt(self.billable_hours) <= 0:
			frappe.throw(
				"Total billable hours is zero or empty. Please ensure there are billable hours before submitting, "
				"as a Delivery Note will be created."
			)

	def _create_dn_from_timesheets(self):
		try:
			self.validate_timesheet_hours_for_delivery_note()
			hours = flt(self.billable_hours)
			if hours <= 0:
				frappe.throw("Total billing hours is zero. Delivery Note cannot be created.")
			if not self.sales_order:
				frappe.throw(
					frappe._("Select a Sales Order on this summary to create a Delivery Note from billable hours.")
				)
			so_line = _so_line_for_billable_hours(self.sales_order)
			so_customer = frappe.db.get_value("Sales Order", self.sales_order, "customer")
			customer = frappe.db.get_value("Implementation", self.implementation, "customer")
			if not customer:
				frappe.throw("Implementation has no Customer.")
			if so_customer and customer and so_customer != customer:
				frappe.throw(
					frappe._("Sales Order customer does not match the customer on this Implementation.")
				)
			company = _company_for_customer(customer)
			if not company:
				frappe.throw("No Company found. Set default Company in Global Defaults.")
			uom = so_line.uom or so_line.stock_uom
			stock_uom = so_line.stock_uom or so_line.uom
			cf = flt(so_line.conversion_factor, 9) or 1
			rate = flt(so_line.rate)
			spl = frappe.db.get_value("Sales Order", self.sales_order, "selling_price_list")
			dn_items = {
				"item_code": so_line.item_code,
				"item_name": so_line.item_name,
				"qty": hours,
				"uom": uom,
				"stock_uom": stock_uom,
				"conversion_factor": cf,
				"rate": rate,
				"amount": flt(rate * hours, 2),
				"against_sales_order": self.sales_order,
				"so_detail": so_line.name,
				"allow_zero_valuation_rate": 1,
				"custom_against_monthly_implementation_summary": self.name,
			}
			dn = frappe.get_doc({
				"doctype": "Delivery Note",
				"customer": customer,
				"company": company,
				"custom_implementation": self.implementation,
				"selling_price_list": spl,
				"items": [dn_items],
			})
			dn.insert()
			self.delivery_note = dn.name
			self.db_set("delivery_note", dn.name)
			frappe.msgprint(f"Delivery Note {dn.name} created with {hours:.2f} Hour(s).")
			return dn.name
		except Exception as e:
			frappe.throw(f"Error creating Delivery Note: {str(e)}")

	def _build_dn_items_from_mis_dni(self):
		if not self.sales_order:
			frappe.throw("Sales Order is required to fetch rates for Delivery Note items.")

		items = []
		for row in self.delivery_note_item:
			ic = row.item_code
			if not ic:
				continue

			qty = flt(row.qty)
			if qty <= 0:
				continue

			so_detail = getattr(row, "so_detail", None)
			if not so_detail and getattr(row, "custom_ref_doc", None):
				so_detail = frappe.db.get_value(
					"Delivery Note Item",
					{
						"parent": row.custom_ref_doc,
						"item_code": ic,
						"parenttype": "Delivery Note",
					},
					"so_detail",
				)

			so_item = None
			if so_detail and frappe.db.exists("Sales Order Item", {"name": so_detail, "parent": self.sales_order}):
				so_item = frappe.db.get_value(
					"Sales Order Item",
					so_detail,
					["name", "item_code", "item_name", "item_group", "stock_uom", "uom", "conversion_factor", "rate"],
					as_dict=True,
				)
			else:
				so_item_name = frappe.db.get_value(
					"Sales Order Item",
					{"parent": self.sales_order, "item_code": ic},
					"name",
				)
				if so_item_name:
					so_item = frappe.db.get_value(
						"Sales Order Item",
						so_item_name,
						["name", "item_code", "item_name", "item_group", "stock_uom", "uom", "conversion_factor", "rate"],
						as_dict=True,
					)

			if not so_item:
				frappe.throw(
					"No matching Sales Order Item found for item {0} in Sales Order {1}.".format(ic, self.sales_order)
				)

			rate = flt(so_item.rate)
			cf = flt(so_item.conversion_factor, 9) or flt(row.conversion_factor, 9) or 1
			uom = so_item.uom or row.uom
			stock_uom = so_item.stock_uom or row.stock_uom or uom

			item_row = {
				"item_code": so_item.item_code or ic,
				"item_name": so_item.item_name or row.item_name or frappe.db.get_value("Item", ic, "item_name"),
				"item_group": so_item.item_group or row.item_group,
				"qty": qty,
				"stock_uom": stock_uom,
				"uom": uom,
				"conversion_factor": cf,
				"rate": rate,
				"amount": flt(rate * qty, 2),
				"expense_account": row.expense_account,
				"cost_center": row.cost_center,
				"allow_zero_valuation_rate": 1,
				"against_sales_order": self.sales_order,
				"so_detail": so_item.name,
			}
			items.append(item_row)

		return items

	def _sync_delivery_note_from_mis_items_for_submit(self):
		if not self.delivery_note_item:
			return

		dn_name = self._get_linked_dn_name(persist_link=True)
		if dn_name:
			dn_status = cint(frappe.db.get_value("Delivery Note", dn_name, "docstatus") or 0)
			if dn_status == 0:
				self.update_delivery_note_from_mis_items()
			elif dn_status == 2:
				frappe.throw(frappe._("Cannot use cancelled Delivery Note {0}.").format(frappe.bold(dn_name)))
			return

		self._create_dn_from_mis_dni()

	def _create_dn_from_mis_dni(self):
		if not self.delivery_note_item:
			frappe.throw("No items in Delivery Note Item table. Add items before submitting.")
		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			frappe.throw("Implementation has no Customer.")
		company = _company_for_customer(customer)
		if not company:
			frappe.throw("No Company found. Set default Company in Global Defaults.")
		items = self._build_dn_items_from_mis_dni()
		if not items:
			frappe.throw("No valid items in Delivery Note Item table.")
		dn = frappe.get_doc({
			"doctype": "Delivery Note",
			"customer": customer,
			"company": company,
			"custom_implementation": self.implementation,
			"items": items,
		})
		dn.insert()
		self.delivery_note = dn.name
		self.db_set("delivery_note", dn.name)
		for row in self.delivery_note_item:
			row.custom_ref_doc = dn.name
		self.save()
		self._update_timesheets_delivery_note(dn.name)
		return dn.name

	def update_delivery_note_from_mis_items(self):
		try:
			dn_name = self._get_linked_dn_name()
			if not dn_name:
				frappe.throw("No Delivery Note linked to this Monthly Implementation Summary.")
			dn = frappe.get_doc("Delivery Note", dn_name)
			if dn.docstatus == 2:
				frappe.throw("Cannot update Delivery Note as it is cancelled.")
			if not self.delivery_note_item:
				frappe.throw("No items in Delivery Note Item table. Add items before submitting.")
			items = self._build_dn_items_from_mis_dni()
			dn.items = []
			for it in items:
				dn.append("items", it)
			dn.save()
			self._update_timesheets_delivery_note(dn.name)
			frappe.msgprint(f"Delivery Note {dn.name} updated from Monthly Implementation Summary items.")
		except Exception as e:
			frappe.throw(f"Error updating Delivery Note: {str(e)}")

	def _update_timesheets_delivery_note(self, dn_name):
		if not dn_name or not self.timesheets_table:
			return
		for row in self.timesheets_table:
			ts = getattr(row, "timesheet", None)
			if ts and frappe.db.exists("Timesheet", ts):
				frappe.db.set_value("Timesheet", ts, "custom_delivery_note", dn_name)

	def _get_linked_dn_name(self, persist_link=True):
		"""Resolve a Delivery Note for this MIS.

		When persist_link is True, found DN is written to this document (and db_set for side paths).
		When False, only returns the name — does not set ``delivery_note`` on the doc.
		"""
		if self.delivery_note:
			ds = frappe.db.get_value("Delivery Note", self.delivery_note, "docstatus")
			if ds is not None and int(ds) != 2:
				return self.delivery_note
		dn_name = None
		if self.name:
			dn_name = frappe.db.get_value(
				"Delivery Note Item",
				{"custom_against_monthly_implementation_summary": self.name},
				"parent",
			)
		if dn_name:
			if persist_link:
				self.delivery_note = dn_name
				self.db_set("delivery_note", dn_name, update_modified=False)
			return dn_name
		if self.sales_order and self.implementation:
			row = frappe.db.sql(
				"""
				select dn.name
				from `tabDelivery Note` dn
				inner join `tabDelivery Note Item` dni on dni.parent = dn.name
					and dni.against_sales_order = %(so)s
				where dn.docstatus != 2 and dn.custom_implementation = %(impl)s
				order by dn.modified desc
				limit 1
				""",
				{"so": self.sales_order, "impl": self.implementation},
				as_list=True,
			)
			if row:
				dn_name = row[0][0]
				if persist_link:
					self.delivery_note = dn_name
					self.db_set("delivery_note", dn_name, update_modified=False)
				return dn_name
		if self.implementation:
			row = frappe.db.sql(
				"""
				select dn.name
				from `tabDelivery Note` dn
				where dn.docstatus != 2 and dn.custom_implementation = %(impl)s
				order by dn.modified desc
				limit 1
				""",
				{"impl": self.implementation},
				as_list=True,
			)
			if row:
				dn_name = row[0][0]
				if persist_link:
					self.delivery_note = dn_name
					self.db_set("delivery_note", dn_name, update_modified=False)
				return dn_name
		return None

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
				},
			)


@frappe.whitelist()
def create_delivery_note(docname: str, sales_order=None, delivery_note_item=None):
	_require_docname(docname)
	if sales_order:
		dn_name = _create_dn_from_sales_order(docname, sales_order, delivery_note_item)
	else:
		doc = frappe.get_doc("Monthly Implementation Summary", docname)
		old_dn = doc.delivery_note
		dn_name = doc._create_dn_from_timesheets()
		update_dn_table_in_summary(docname, dn_name, old_dn=old_dn)
	return {"status": "ok", "dn_name": dn_name}


def _create_dn_from_sales_order(docname, sales_order, delivery_note_item=None):
	"""Create a draft Delivery Note using ERPNext's Sales Order → DN mapping (remaining qty per line)."""
	try:
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		mis_doc = frappe.get_doc("Monthly Implementation Summary", docname)
		if not mis_doc.implementation:
			frappe.throw(frappe._("Implementation is required on Monthly Implementation Summary."))
		so_name = (mis_doc.sales_order or sales_order or "").strip()
		if not so_name:
			frappe.throw(frappe._("Select a Sales Order on the Monthly Implementation Summary."))
		if mis_doc.sales_order and sales_order and mis_doc.sales_order != sales_order:
			frappe.throw(
				frappe._("Sales Order on the form ({0}) does not match the request ({1}).").format(
					mis_doc.sales_order, sales_order
				)
			)
		dn = make_delivery_note(so_name)
		if not dn.items:
			frappe.throw(
				frappe._(
					"Nothing left to deliver against Sales Order {0}. All line items may already be fully delivered."
				).format(so_name)
			)

		for item in dn.items:
			if item.so_detail:
				soi = frappe.get_doc("Sales Order Item", item.so_detail)

				# Force SO values and ignore pricing rule values
				item.rate = flt(soi.rate)
				item.net_rate = flt(soi.rate)
				item.price_list_rate = flt(soi.rate)

				item.amount = flt(item.qty * item.rate)
				item.net_amount = flt(item.qty * item.net_rate)

				item.discount_percentage = 0

		dn.flags.ignore_pricing_rule = True
		dn.ignore_pricing_rule = 1
		dn.custom_implementation = mis_doc.implementation
		dn.insert()
		old_dn = frappe.db.get_value("Monthly Implementation Summary", docname, "delivery_note")
		frappe.db.set_value("Monthly Implementation Summary", docname, "delivery_note", dn.name)
		frappe.db.commit()
		update_dn_table_in_summary(docname, dn.name, old_dn=old_dn)
		return dn.name
	except Exception as e:
		frappe.throw(str(e))


def update_dn_table_in_summary(docname, dn_name, old_dn=None, existing_rows=None):
	if not docname or not dn_name:
		return
	dn_doc = frappe.get_doc("Delivery Note", dn_name)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.reload()
	dn_refs = {dn_name}
	if old_dn:
		dn_refs.add(old_dn)
	doc.delivery_note_item = [
		r for r in (doc.delivery_note_item or []) if getattr(r, "custom_ref_doc", None) not in dn_refs
	]
	for item in dn_doc.items:
		ao = getattr(item, "against_sales_order", None)
		if doc.sales_order and ao and ao != doc.sales_order:
			continue
		qty = flt(item.qty)
		rate = _resolve_rate_for_mis_from_dn_row(doc, item)
		icode = item.item_code
		iname = item.item_name
		igroup = item.item_group
		suom = item.stock_uom or item.uom
		uom = item.uom
		cf = flt(item.conversion_factor, 9) or 1
		if (
			doc.sales_order
			and getattr(item, "so_detail", None)
			and frappe.db.exists("Sales Order Item", {"name": item.so_detail, "parent": doc.sales_order})
		):
			soi = frappe.db.get_value(
				"Sales Order Item",
				item.so_detail,
				["item_code", "item_name", "item_group", "stock_uom", "uom", "conversion_factor", "rate"],
				as_dict=True,
			)
			if soi:
				icode = soi.item_code or icode
				iname = soi.item_name or iname
				igroup = soi.item_group or igroup
				suom = soi.stock_uom or suom
				uom = soi.uom or uom
				cf = flt(soi.conversion_factor, 9) or cf
				rate = flt(soi.rate)
		row_data = {
			"item_code": icode,
			"item_name": iname,
			"item_group": igroup,
			"qty": qty,
			"stock_uom": suom,
			"uom": uom,
			"conversion_factor": cf,
			"rate": rate,
			"amount": flt(rate * qty, 2),
			"expense_account": item.expense_account,
			"cost_center": item.cost_center,
			"custom_ref_doc": dn_name,
		}
		doc.append("delivery_note_item", row_data)
	doc.save()


@frappe.whitelist()
def submit_mis_dn_action(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.reload()
	doc._sync_delivery_note_from_mis_items_for_submit()
	# Sub-methods may stamp timesheets; repeat after reload so DB ``delivery_note`` / links are visible.
	doc.reload()
	dn_name = doc._resolve_dn_name_for_timesheet_stamp()
	if dn_name:
		doc._update_timesheets_delivery_note(dn_name)
	return {"status": "ok"}


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
	"""Update Timesheet Detail billing_hours and hours, then save in draft.

	This keeps billable edits from the MIS dialog in sync with Timesheet worked hours
	so MIS totals reflect the same value after refresh.
	"""
	if cint(ts_doc.docstatus) != 0:
		frappe.throw(frappe._("Timesheet {0} is not in Draft.").format(frappe.bold(ts_doc.name)))

	logs = list(ts_doc.get("time_logs") or [])
	if not logs:
		frappe.throw(frappe._("Timesheet {0} has no time logs.").format(frappe.bold(ts_doc.name)))

	target = max(flt(target_billable_hours), 0)
	total_hours = flt(sum(flt(getattr(log, "hours", 0)) for log in logs), 2)

	if total_hours <= 0:
		for idx, log in enumerate(logs):
			bill = target if idx == 0 else 0
			log.billing_hours = bill
			log.hours = bill
			if getattr(log, "from_time", None):
				log.to_time = add_to_date(log.from_time, hours=bill)
		ts_doc.save(ignore_permissions=True)
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
		log.hours = bill
		if getattr(log, "from_time", None):
			log.to_time = add_to_date(log.from_time, hours=bill)

	ts_doc.save(ignore_permissions=True)
	ts_doc.reload()
	total_hours = flt(sum(flt(getattr(log, "hours", 0)) for log in (ts_doc.time_logs or [])), 2)
	total_billable_hours = flt(sum(flt(getattr(log, "billing_hours", 0)) for log in (ts_doc.time_logs or [])), 2)
	frappe.db.set_value(
		"Timesheet",
		ts_doc.name,
		{"total_hours": total_hours, "total_billable_hours": total_billable_hours},
		update_modified=False,
	)


@frappe.whitelist()
def get_timesheet_approval_rows(
	docname: str,
	employee=None,
	project=None,
	date_from=None,
	date_to=None,
):
	_require_docname(docname)

	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")

	employee_filter = (employee or "").strip()
	project_filter = (project or "").strip()
	from_date = getdate(date_from) if date_from else None
	to_date = getdate(date_to) if date_to else None

	base_rows = list(doc.timesheets_table or [])

	timesheet_names = [
		(str(getattr(r, "timesheet", "") or "").strip())
		for r in base_rows
		if (str(getattr(r, "timesheet", "") or "").strip())
	]

	meta_by_name = {}
	description_by_timesheet = {}

	if timesheet_names:
		timesheet_names = list(set(timesheet_names))

		ts_fields = ["name", "docstatus", "status", "custom_rating"]

		for ts in frappe.get_all(
			"Timesheet",
			filters={"name": ["in", timesheet_names]},
			fields=ts_fields,
		):
			meta_by_name[ts.name] = ts

		# Fetch description from the Time Sheets child table
		for time_sheet in frappe.get_all(
			"Timesheet Detail",
			filters={
				"parent": ["in", timesheet_names],
				"parenttype": "Timesheet",
			},
			fields=["parent", "description"],
			order_by="idx asc",
		):
			# Keep the first Time Sheets row's description.
			# This preserves the existing single-description display.
			if time_sheet.parent not in description_by_timesheet:
				description_by_timesheet[time_sheet.parent] = (
					time_sheet.description or ""
				)

	result = []

	for row in base_rows:
		ts_name = (getattr(row, "timesheet", "") or "").strip()
		emp_name = (getattr(row, "employee_name", "") or "").strip()
		row_project = (getattr(row, "project", "") or "").strip()
		row_employee = (getattr(row, "employee", "") or "").strip()

		row_date_raw = getattr(row, "date", None)
		row_date = getdate(row_date_raw) if row_date_raw else None

		meta = meta_by_name.get(ts_name)

		docstatus = cint(meta.docstatus) if meta else 0
		status = (meta.status if meta else "") or ""

		is_pending = _timesheet_is_pending_for_approval(
			docstatus,
			status,
		)

		if employee_filter:
			if row_employee != employee_filter and emp_name != employee_filter:
				continue

		if project_filter:
			if row_project != project_filter:
				continue

		if from_date and (not row_date or row_date < from_date):
			continue

		if to_date and (not row_date or row_date > to_date):
			continue

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
				"docstatus": docstatus,
				"status": status,
				"is_pending": 1 if is_pending else 0,
				# Rating comes from the Timesheet parent
				"rating": (meta.custom_rating if meta else "") or "",
				# Description comes from the Timesheet -> Time Sheets child table
				"description": description_by_timesheet.get(
					ts_name,
					"",
				),
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
		doc.save(ignore_permissions=True)
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
def create_sales_invoice_from_mis(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.check_permission("read")
	has_sales_invoice_field = bool(doc.meta.get_field("sales_invoice"))
	mis_sales_invoice = getattr(doc, "sales_invoice", None) if has_sales_invoice_field else None

	if cint(doc.docstatus) != 1:
		frappe.throw(frappe._("Monthly Implementation Summary must be submitted before creating a Sales Invoice."))

	delivery_note = (doc.delivery_note or "").strip()
	if not delivery_note:
		frappe.throw(frappe._("No Delivery Note linked to this Monthly Implementation Summary."))

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

	existing_si = None
	if mis_sales_invoice and frappe.db.exists(
		"Sales Invoice", {"name": mis_sales_invoice, "docstatus": ["!=", 2]}
	):
		existing_si = mis_sales_invoice
	else:
		existing_si = _find_existing_sales_invoice_for_delivery_note(delivery_note)

	if existing_si:
		if has_sales_invoice_field and mis_sales_invoice != existing_si:
			doc.db_set("sales_invoice", existing_si, update_modified=False)
		si_link = frappe.utils.get_link_to_form("Sales Invoice", existing_si)
		frappe.throw(
			frappe._("A Sales Invoice {0} already exists for Delivery Note {1}.").format(
				si_link,
				frappe.bold(delivery_note),
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
	if has_sales_invoice_field:
		doc.db_set("sales_invoice", si_doc.name, update_modified=False)

	return {"status": "ok", "sales_invoice": si_doc.name}


@frappe.whitelist()
def update_dn_from_mis_items(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc.update_delivery_note_from_mis_items()
	return {"status": "ok"}


@frappe.whitelist()
def create_dn_from_mis_dni(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summary", docname)
	doc._create_dn_from_mis_dni()
	return {"status": "ok"}


def _mis_after_dn_submit(dn):
	"""(mis_names_get_timesheet_stamp, mis_names_to_save) for this submitted Delivery Note."""
	stamp = {n for n in frappe.get_all(
		"Monthly Implementation Summary",
		filters={"delivery_note": dn.name, "docstatus": ["!=", 2]},
		pluck="name",
	) if n}
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
	impl = {getattr(dn, "custom_implementation", None)}
	impl.discard(None)
	for it in dn.get("items") or []:
		so = getattr(it, "against_sales_order", None)
		if not so:
			continue
		i = frappe.db.get_value("Sales Order", so, "custom_implementation")
		if i:
			impl.add(i)
	for i in impl:
		for n in frappe.get_all(
			"Monthly Implementation Summary",
			filters={"implementation": i, "docstatus": ["in", [0, 1]]},
			pluck="name",
		):
			if n:
				save.add(n)
	return stamp, save


def update_mis_timesheets_on_delivery_note_submit(doc, method=None):
	if not doc or getattr(doc, "doctype", None) != "Delivery Note" or cint(doc.docstatus) != 1:
		return
	stamp, save = _mis_after_dn_submit(doc)
	dn_name = doc.name
	for mis_name in save:
		if not mis_name or not frappe.db.exists("Monthly Implementation Summary", mis_name):
			continue
		m = frappe.get_doc("Monthly Implementation Summary", mis_name)
		m.reload()
		if mis_name in stamp:
			m._update_timesheets_delivery_note(dn_name)
		m._refresh_sales_order_status_and_financials()
		try:
			m.flags.ignore_permissions = True
			m.flags.ignore_validate_update_after_submit = True
			m.save()
		except Exception:
			frappe.log_error(title="MIS refresh after Delivery Note submit", message=frappe.get_traceback())
