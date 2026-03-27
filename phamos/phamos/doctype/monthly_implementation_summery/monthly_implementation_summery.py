# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, flt
from frappe.query_builder import DocType, Order

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


def _phamos_settings_item():
	return frappe.db.get_single_value("phamos Settings", "item")


def _item_selling_rate(item_code, uom=None):
	filters = {"item_code": item_code, "selling": 1}
	if uom:
		filters["uom"] = uom
	rate = frappe.db.get_value("Item Price", filters, "price_list_rate", order_by="valid_from desc")
	if rate is not None:
		return flt(rate, 2)
	if uom:
		rate = frappe.db.get_value(
			"Item Price", {"item_code": item_code, "selling": 1}, "price_list_rate", order_by="valid_from desc"
		)
	return flt(rate, 2) if rate is not None else 0


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


def _dn_line_for_item(dn_doc, item_code):
	if not dn_doc or not item_code:
		return None
	for itm in dn_doc.items:
		if itm.item_code == item_code:
			return itm
	return None


def _resolve_rate_for_mis_from_dn_row(mis_doc, dn_item):
	"""Create-DN sync: DN / SO only, never Item Price."""
	r = _rate_from_dn_line(dn_item)
	if not r and getattr(dn_item, "so_detail", None):
		r = _rate_from_so_detail(dn_item.so_detail)
	if not r and mis_doc.sales_order:
		r = _rate_from_sales_order(mis_doc.sales_order, dn_item.item_code)
	return flt(r, 2)


def _rate_for_timesheet_row(mis_doc, item_code, dn_doc):
	"""Timesheet update: DN/SO rate if item on linked DN or SO; else Item Price."""
	dn_line = _dn_line_for_item(dn_doc, item_code)
	on_so = bool(
		mis_doc.sales_order
		and frappe.db.exists("Sales Order Item", {"parent": mis_doc.sales_order, "item_code": item_code})
	)
	if dn_line or on_so:
		r = _rate_from_dn_line(dn_line) if dn_line else 0
		if not r and mis_doc.sales_order:
			r = _rate_from_sales_order(mis_doc.sales_order, item_code)
		if r:
			return flt(r, 2)
	return _item_selling_rate(item_code, uom="Hour")


def _get_previous_month_year_and_name(year_str, month_name):
	if not year_str or not month_name:
		return None, None
	month_num = MONTH_NAME_TO_NUM.get(month_name)
	if not month_num:
		return None, None
	try:
		year_int = int(str(year_str).strip())
	except (ValueError, TypeError):
		return None, None
	if month_num == 1:
		return str(year_int - 1), "December"
	names = list(MONTH_NAME_TO_NUM.keys())
	return str(year_int), names[month_num - 2]


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


class MonthlyImplementationSummery(Document):
	def validate(self):
		self.validate_year()
		self.validate_month()
		self.validate_duplicate_record()
		if self.implementation and self.year and self.month and not self.timesheets_table:
			self.set_timesheets_table()
		self._recalculate_totals_from_timesheets_table()
		self._recalculate_delivery_note_item_amounts()
		self.populate_financial_history_fields()

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

	def validate_phamos_settings_item(self):
		if not _phamos_settings_item():
			frappe.throw(
				"No item configured in Phamos Settings. Please set the default Item in Phamos Settings "
				"(Monthly Implementation Summery tab) before submitting."
			)

	def validate_timesheet_hours_for_delivery_note(self):
		if flt(self.billable_hours) <= 0:
			frappe.throw(
				"Total billable hours is zero or empty. Please ensure there are billable hours before submitting, "
				"as a Delivery Note will be created."
			)

	def _create_dn_from_timesheets(self):
		try:
			self.validate_phamos_settings_item()
			self.validate_timesheet_hours_for_delivery_note()
			hours = flt(self.billable_hours)
			if hours <= 0:
				frappe.throw("Total billing hours is zero. Delivery Note cannot be created.")
			item = _phamos_settings_item()
			if not item:
				frappe.throw("No item configured in Phamos Settings.")
			customer = frappe.db.get_value("Implementation", self.implementation, "customer")
			if not customer:
				frappe.throw("Implementation has no Customer.")
			company = _company_for_customer(customer)
			if not company:
				frappe.throw("No Company found. Set default Company in Global Defaults.")
			dn = frappe.get_doc({
				"doctype": "Delivery Note",
				"customer": customer,
				"company": company,
				"custom_implementation": self.implementation,
				"items": [{
					"item_code": item,
					"qty": hours,
					"uom": "Hour",
					"allow_zero_valuation_rate": 1,
					"custom_against_monthly_implementation_summery": self.name,
				}],
			})
			dn.insert()
			self.delivery_note = dn.name
			self.db_set("delivery_note", dn.name)
			frappe.msgprint(f"Delivery Note {dn.name} created with {hours:.2f} Hour(s).")
			return dn.name
		except Exception as e:
			frappe.log_error(f"Error creating Delivery Note for {self.name}: {str(e)}")
			frappe.throw(f"Error creating Delivery Note: {str(e)}")

	def update_mis_delivery_note_item_from_timesheets(self, existing_rows=None):
		self.validate_phamos_settings_item()
		self.validate_timesheet_hours_for_delivery_note()
		hours = flt(self.billable_hours)
		if hours <= 0:
			frappe.throw("Total billable hours is zero. Nothing to add.")
		item_code = _phamos_settings_item()
		if not item_code:
			frappe.throw("No item configured in Phamos Settings.")
		self.reload()
		item_name = frappe.db.get_value("Item", item_code, "item_name")
		item_group = frappe.db.get_value("Item", item_code, "item_group")
		dn_doc = frappe.get_doc("Delivery Note", self.delivery_note) if self.delivery_note else None
		rate = _rate_for_timesheet_row(self, item_code, dn_doc)
		row_data = {
			"item_code": item_code,
			"item_name": item_name,
			"item_group": item_group,
			"qty": hours,
			"stock_uom": "Hour",
			"uom": "Hour",
			"conversion_factor": 1,
			"rate": rate,
			"amount": flt(rate * hours, 2),
			"custom_ref_doc": self.name,
		}
		idx = None
		for i, row in enumerate(self.delivery_note_item or []):
			ref = getattr(row, "custom_ref_doc", None)
			if row.item_code == item_code and (ref == self.name or not ref):
				idx = i
				break
		if idx is not None:
			for k, v in row_data.items():
				setattr(self.delivery_note_item[idx], k, v)
		else:
			self.append("delivery_note_item", row_data)
		self.save()

	def _build_dn_items_from_mis_dni(self):
		grouped = {}
		for row in self.delivery_note_item:
			ic = row.item_code
			if not ic:
				continue
			qty = flt(row.qty)
			amount = flt(row.amount)
			so_detail = getattr(row, "so_detail", None) or (
				row.get("so_detail") if isinstance(row, dict) else None
			)
			key = (ic, so_detail)
			if key not in grouped:
				grouped[key] = {
					"item_code": ic,
					"item_name": row.item_name or frappe.db.get_value("Item", ic, "item_name"),
					"item_group": row.item_group,
					"qty": qty,
					"amount": amount,
					"stock_uom": row.stock_uom or row.uom,
					"uom": row.uom,
					"conversion_factor": flt(row.conversion_factor, 9) or 1,
					"expense_account": row.expense_account,
					"cost_center": row.cost_center,
					"so_detail": so_detail,
				}
			else:
				grouped[key]["qty"] += qty
				grouped[key]["amount"] += amount
		items = []
		for g in grouped.values():
			qty = g["qty"]
			g["rate"] = flt(g["amount"] / qty, 2) if qty else 0
			g["amount"] = flt(g["amount"], 2)
			item_row = {
				"item_code": g["item_code"],
				"item_name": g["item_name"],
				"item_group": g["item_group"],
				"qty": qty,
				"stock_uom": g["stock_uom"],
				"uom": g["uom"],
				"conversion_factor": g["conversion_factor"],
				"rate": g["rate"],
				"amount": g["amount"],
				"expense_account": g["expense_account"],
				"cost_center": g["cost_center"],
				"allow_zero_valuation_rate": 1,
			}
			if g.get("so_detail"):
				item_row["against_sales_order"] = self.sales_order
				item_row["so_detail"] = g["so_detail"]
			else:
				item_row["custom_against_monthly_implementation_summery"] = self.name
			items.append(item_row)
		return items

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
				frappe.throw("No Delivery Note linked to this Monthly Implementation Summery.")
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
			frappe.msgprint(f"Delivery Note {dn.name} updated from Monthly Implementation Summery items.")
		except Exception as e:
			frappe.log_error(f"Error updating Delivery Note from MIS items for {self.name}: {str(e)}")
			frappe.throw(f"Error updating Delivery Note: {str(e)}")

	def _update_timesheets_delivery_note(self, dn_name):
		if not dn_name or not self.timesheets_table:
			return
		for row in self.timesheets_table:
			ts = getattr(row, "timesheet", None)
			if ts and frappe.db.exists("Timesheet", ts):
				frappe.db.set_value("Timesheet", ts, "custom_delivery_note", dn_name)

	def _get_linked_dn_name(self):
		if self.delivery_note:
			return self.delivery_note
		dn_name = frappe.db.get_value(
			"Delivery Note Item",
			{"custom_against_monthly_implementation_summery": self.name},
			"parent",
		)
		if dn_name:
			self.delivery_note = dn_name
			self.db_set("delivery_note", dn_name)
		return dn_name

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
		existing = frappe.get_all(
			"Monthly Implementation Summery",
			filters={
				"implementation": self.implementation,
				"year": self.year,
				"month": self.month,
				"name": ["!=", self.name],
				"docstatus": ["!=", 2],
			},
			fields=["name"],
			limit=1,
		)
		if not existing:
			return
		link = frappe.utils.get_link_to_form("Monthly Implementation Summery", existing[0].name)
		impl = frappe.utils.get_link_to_form("Implementation", self.implementation)
		frappe.throw(
			f"A Monthly Implementation Summery record {link} already exists for "
			f"Implementation {impl}, Year {self.year} and Month {self.month}."
		)

	def _recalculate_totals_from_timesheets_table(self):
		if not self.timesheets_table:
			return
		self.total_hours = flt(sum(flt(r.total_hours) for r in self.timesheets_table), precision=2)
		self.billable_hours = flt(sum(flt(r.billable_hours) for r in self.timesheets_table), precision=2)

	def set_timesheets_table(self):
		prev_year, prev_month = _get_previous_month_year_and_name(self.year, self.month)
		if not prev_year or not prev_month:
			self.timesheets_table = []
			return
		from_date, to_date = _get_month_date_range(prev_year, prev_month)
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
		doc = frappe.get_doc("Monthly Implementation Summery", docname)
		old_dn = doc.delivery_note
		dn_name = doc._create_dn_from_timesheets()
		update_dn_table_in_summary(docname, dn_name, old_dn=old_dn)
	return {"status": "ok", "dn_name": dn_name}


def _create_dn_from_sales_order(docname, sales_order, delivery_note_item=None):
	try:
		items = get_items_for_delivery_note(docname, sales_order)
		if not items:
			frappe.throw("No items in Sales Order.")
		so_doc = frappe.get_doc("Sales Order", sales_order)
		dn = frappe.get_doc({
			"doctype": "Delivery Note",
			"customer": so_doc.customer,
			"project": so_doc.project,
			"palette": 0,
			"paket": 0,
			"items": items,
			"docstatus": 0,
			"posting_date": frappe.utils.nowdate(),
			"selling_price_list": so_doc.selling_price_list,
		})
		dn.insert()
		old_dn = frappe.db.get_value("Monthly Implementation Summery", docname, "delivery_note")
		frappe.db.set_value("Monthly Implementation Summery", docname, "delivery_note", dn.name)
		frappe.db.commit()
		update_dn_table_in_summary(docname, dn.name, old_dn=old_dn)
		return dn.name
	except Exception as e:
		frappe.log_error(f"Error creating DN for {docname}: {str(e)}")
		frappe.throw(str(e))


def update_dn_table_in_summary(docname, dn_name, old_dn=None, existing_rows=None):
	if not docname or not dn_name:
		return
	dn_doc = frappe.get_doc("Delivery Note", dn_name)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.reload()
	dn_refs = {dn_name}
	if old_dn:
		dn_refs.add(old_dn)
	doc.delivery_note_item = [
		r for r in (doc.delivery_note_item or []) if getattr(r, "custom_ref_doc", None) not in dn_refs
	]
	for item in dn_doc.items:
		rate = _resolve_rate_for_mis_from_dn_row(doc, item)
		amount = flt(rate * flt(item.qty), 2)
		row_data = {
			"item_code": item.item_code,
			"item_name": item.item_name,
			"item_group": item.item_group,
			"qty": item.qty,
			"stock_uom": item.stock_uom or item.uom,
			"uom": item.uom,
			"conversion_factor": flt(item.conversion_factor, 9) or 1,
			"rate": rate,
			"amount": amount,
			"expense_account": item.expense_account,
			"cost_center": item.cost_center,
			"custom_ref_doc": dn_name,
		}
		if getattr(item, "against_sales_order", None) and getattr(item, "so_detail", None):
			row_data["against_sales_order"] = item.against_sales_order
			row_data["so_detail"] = item.so_detail
		doc.append("delivery_note_item", row_data)
	doc.save()


@frappe.whitelist()
def update_delivery_note_from_summary(docname: str, delivery_note_item=None):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.update_mis_delivery_note_item_from_timesheets(existing_rows=delivery_note_item)
	return {"status": "ok", "message": frappe._("Delivery Note Items updated from current timesheets.")}


@frappe.whitelist()
def submit_mis_dn_action(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.reload()
	if doc._get_linked_dn_name():
		doc.update_delivery_note_from_mis_items()
	else:
		doc._create_dn_from_mis_dni()
	return {"status": "ok"}


@frappe.whitelist()
def update_dn_from_mis_items(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.update_delivery_note_from_mis_items()
	return {"status": "ok"}


@frappe.whitelist()
def create_dn_from_mis_dni(docname: str):
	_require_docname(docname)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc._create_dn_from_mis_dni()
	return {"status": "ok"}


def get_items_for_delivery_note(docname, sales_order):
	"""Build Delivery Note Item rows from Sales Order. `docname` kept for API compatibility."""
	if not sales_order:
		return []
	so_doc = frappe.get_doc("Sales Order", sales_order)
	out = []
	for so_item in so_doc.items:
		out.append(
			frappe.get_doc({
				"doctype": "Delivery Note Item",
				"item_code": so_item.item_code,
				"delivery_date": so_item.delivery_date.strftime("%Y-%m-%d") if so_item.delivery_date else "",
				"conversion_factor": so_item.conversion_factor,
				"qty": so_item.qty,
				"rate": so_item.rate,
				"uom": so_item.uom,
				"idx": so_item.idx,
				"warehouse": so_item.warehouse,
				"against_sales_order": so_doc.name,
				"so_detail": so_item.name,
			})
		)
	return out
