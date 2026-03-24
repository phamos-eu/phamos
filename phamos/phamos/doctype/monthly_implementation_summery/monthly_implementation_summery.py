# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, formatdate, escape_html, get_url_to_form, flt
from frappe.query_builder import DocType, Order
from datetime import datetime

from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
from phamos.phamos.doctype.implementation.implementation import (
	get_financial_history as get_implementation_financial_history,
)

# Map month name (as in Select options) to month number 1-12
MONTH_NAME_TO_NUM = {
	"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
	"July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}
# Valid year range for validation (inclusive)
YEAR_MIN = 2000
YEAR_MAX = 2100


class MonthlyImplementationSummery(Document):
	def validate(self):
		self.validate_year()
		self.validate_month()
		self.validate_duplicate_record()
		if self.implementation and self.year and self.month and not self.timesheets_table:
			self.set_timesheets_table()
		self._recalculate_totals_from_timesheets_table()
		self.populate_financial_history_fields()

	def populate_financial_history_fields(self):
		"""Fill sales_order_qty, dn_qty, timesheet_hrs, remaining_hrs, open_so from Implementation KPIs.

		Wraps get_financial_history; requires Implementation.customer (same as desk form).
		"""
		if not self.implementation:
			self._clear_financial_history_fields()
			return

		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			self._clear_financial_history_fields()
			return

		data = get_implementation_financial_history(self.implementation, customer) or {}
		self.sales_order_qty = flt(data.get("sales_order_qty"), 2)
		self.dn_qty = flt(data.get("dn_qty"), 2)
		self.timesheet_hrs = flt(data.get("timesheet_hrs"), 2)
		self.remaining_hrs = flt(data.get("remaining_hrs"), 2)
		self.open_so = 1 if data.get("open_so") else 0

	def _clear_financial_history_fields(self):
		self.sales_order_qty = 0
		self.dn_qty = 0
		self.timesheet_hrs = 0
		self.remaining_hrs = 0
		self.open_so = 0

	def validate_phamos_settings_item(self):
		"""Block save/submit if Phamos Settings has no default item (required for Delivery Note)."""
		item = frappe.db.get_single_value("phamos Settings", "item")
		if not item:
			frappe.throw(
				"No item configured in Phamos Settings. Please set the default Item in Phamos Settings (Monthly Implementation Summery tab) before submitting."
			)

	def validate_timesheet_hours_for_delivery_note(self):
		"""Block submit if total billable hours is zero or empty, as Delivery Note cannot be created."""
		
	
		hours_to_check = flt(self.billable_hours)
		
		if hours_to_check <= 0:
			frappe.throw(
				"Total billable hours is zero or empty. Please ensure there are billable hours before submitting, as a Delivery Note will be created."
			)

	def _create_dn_from_timesheets(self):
		"""Create Delivery Note from timesheet hours (no Sales Order)."""
		try:
			self.validate_phamos_settings_item()
			self.validate_timesheet_hours_for_delivery_note()
			
			# Get billing hours
			total_billing_hours = flt(self.billable_hours)
			if total_billing_hours <= 0:
				frappe.throw("Total billing hours is zero. Delivery Note cannot be created.")
			
			# Get item from settings
			item = frappe.db.get_single_value("phamos Settings", "item")
			if not item:
				frappe.throw("No item configured in Phamos Settings.")
			
			# Get customer from implementation
			customer = frappe.db.get_value("Implementation", self.implementation, "customer")
			if not customer:
				frappe.throw("Implementation has no Customer.")
			
			# Get company
			company = (frappe.db.get_default("company") or 
					  frappe.db.get_value("Customer", customer, "customer_primary_company") or
					  frappe.db.get_single_value("Global Defaults", "default_company"))
			if not company:
				frappe.throw("No Company found. Set default Company in Global Defaults.")
			
			# Create Delivery Note
			dn = frappe.get_doc({
				"doctype": "Delivery Note",
				"customer": customer,
				"company": company,
				"custom_implementation": self.implementation,
				"items": [{
					"item_code": item,
					"qty": total_billing_hours,
					"uom": "Hour",
					"allow_zero_valuation_rate": 1,
					"custom_against_monthly_implementation_summery": self.name
				}]
			})
			dn.insert()
			# Link back to this Monthly Implementation Summery
			self.delivery_note = dn.name
			self.db_set("delivery_note", dn.name)

			frappe.msgprint(f"Delivery Note {dn.name} created with {total_billing_hours:.2f} Hour(s).")
			return dn.name

		except Exception as e:
			frappe.log_error(f"Error creating Delivery Note for {self.name}: {str(e)}")
			frappe.throw(f"Error creating Delivery Note: {str(e)}")

	def update_mis_delivery_note_item_from_timesheets(self, existing_rows=None):
		"""Add or update rows in MIS delivery_note_item from timesheets.

		Does NOT update the linked Delivery Note. DN is updated only on MIS submit.
		Only updates/appends rows with ref_doc = current MIS (timesheet rows).
		Rows with ref_doc = DN name are left untouched.
		Called by 'Update current timesheets hours' button.
		"""
		self.validate_phamos_settings_item()
		self.validate_timesheet_hours_for_delivery_note()
		total_billing_hours = flt(self.billable_hours)
		if total_billing_hours <= 0:
			frappe.throw("Total billable hours is zero. Nothing to add.")

		item_code = frappe.db.get_single_value("phamos Settings", "item")
		if not item_code:
			frappe.throw("No item configured in Phamos Settings.")

		# Use DB as base - reload to preserve all rows including ref_doc=DN rows
		self.reload()

		item_name = frappe.db.get_value("Item", item_code, "item_name")
		item_group = frappe.db.get_value("Item", item_code, "item_group")
		rate = _get_item_selling_rate(item_code, uom="Hour")
		amount = flt(rate * total_billing_hours, 2)
		row_data = {
			"item_code": item_code,
			"item_name": item_name,
			"item_group": item_group,
			"qty": total_billing_hours,
			"stock_uom": "Hour",
			"uom": "Hour",
			"conversion_factor": 1,
			"rate": rate,
			"amount": amount,
			"custom_ref_doc": self.name,  # MIS docname for timesheet rows only
		}

		# Find existing row for timesheet item where ref_doc = current MIS (only touch timesheet rows)
		existing_idx = None
		for i, row in enumerate(self.delivery_note_item or []):
			ref = getattr(row, "custom_ref_doc", None)
			if row.item_code == item_code and (ref == self.name or not ref):
				existing_idx = i
				break

		if existing_idx is not None:
			row = self.delivery_note_item[existing_idx]
			for k, v in row_data.items():
				setattr(row, k, v)
		else:
			self.append("delivery_note_item", row_data)
		self.save()

	def _build_dn_items_from_mis_dni(self):
		"""Build DN items from mis-dni. Separate rows for SO portion and MIS portion (same item_code)."""
		# Group by (item_code, so_detail) - so_detail=None for MIS/timesheet rows
		grouped = {}
		for row in self.delivery_note_item:
			ic = row.item_code
			if not ic:
				continue
			qty = flt(row.qty)
			amount = flt(row.amount)
			so_detail = getattr(row, "so_detail", None) or (row.get("so_detail") if isinstance(row, dict) else None)
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
			# ref_doc=DN (has so_detail): against_sales_order, so_detail. No custom_against_monthly_implementation_summery.
			# ref_doc=MIS: custom_against_monthly_implementation_summery only. No against_sales_order.
			if g.get("so_detail"):
				item_row["against_sales_order"] = self.sales_order
				item_row["so_detail"] = g["so_detail"]
			else:
				item_row["custom_against_monthly_implementation_summery"] = self.name
			items.append(item_row)
		return items

	def _create_dn_from_mis_dni(self):
		"""Create new DN from mis-dni rows. Called on submit when no DN exists."""
		if not self.delivery_note_item:
			frappe.throw("No items in Delivery Note Item table. Add items before submitting.")
		customer = frappe.db.get_value("Implementation", self.implementation, "customer")
		if not customer:
			frappe.throw("Implementation has no Customer.")
		company = (frappe.db.get_default("company") or
			frappe.db.get_value("Customer", customer, "customer_primary_company") or
			frappe.db.get_single_value("Global Defaults", "default_company"))
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
		# Update mis-dni: set ref_doc=dn_name for rows we used
		for row in self.delivery_note_item:
			row.custom_ref_doc = dn.name
		self.save()
		self._update_timesheets_delivery_note(dn.name)
		return dn.name

	def update_delivery_note_from_mis_items(self):
		"""Replace Delivery Note items with rows from delivery_note_item child table in MIS.

		Called on submit when DN already exists. MIS delivery_note_item is the source of truth.
		"""
		try:
			dn_name = self._get_linked_dn_name()
			if not dn_name:
				frappe.throw("No Delivery Note linked to this Monthly Implementation Summery.")

			dn = frappe.get_doc("Delivery Note", dn_name)
			if dn.docstatus == 2:
				frappe.throw("Cannot update Delivery Note as it is cancelled.")

			if not self.delivery_note_item:
				frappe.throw("No items in Delivery Note Item table. Add items before submitting.")

			# Replace DN items with MIS delivery_note_item rows (grouped by item_code, combined qty)
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
		"""Set custom_delivery_note on all Timesheets in timesheets_table."""
		if not dn_name or not self.timesheets_table:
			return
		for row in self.timesheets_table:
			ts_name = getattr(row, "timesheet", None)
			if ts_name and frappe.db.exists("Timesheet", ts_name):
				frappe.db.set_value("Timesheet", ts_name, "custom_delivery_note", dn_name)

	def _get_linked_dn_name(self):
		"""Get linked Delivery Note name, syncing delivery_note field if needed."""
		dn_name = self.delivery_note
		if not dn_name:
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
		"""Validate that year is a valid 4-digit year in allowed range."""
		if not self.year:
			return
		year_str = (self.year or "").strip()
		if not year_str:
			frappe.throw("Year cannot be empty.")
		if len(year_str) != 4 or not year_str.isdigit():
			frappe.throw(
				f"Invalid year format. Use a 4-digit year (e.g. 2024). Got: {frappe.bold(self.year)}"
			)
		year_int = int(year_str)
		if year_int < YEAR_MIN or year_int > YEAR_MAX:
			frappe.throw(
				f"Year must be between {YEAR_MIN} and {YEAR_MAX}. Got: {frappe.bold(self.year)}"
			)

	def validate_month(self):
		"""Validate that month is one of the allowed month names."""
		if self.month and self.month not in MONTH_NAME_TO_NUM:
			frappe.throw(
				f"Invalid month. Choose one of: January, February, March, April, May, June, "
				f"July, August, September, October, November, December. Got: {frappe.bold(self.month)}"
			)

	def validate_duplicate_record(self):
		"""Ensure only one Monthly Implementation Summery per Implementation, Year and Month."""
		if self.implementation and self.year and self.month:
			existing = frappe.get_all('Monthly Implementation Summery',
				filters={
					'implementation': self.implementation,
					'year': self.year,
					'month': self.month,
					'name': ['!=', self.name],
					'docstatus': ['!=', 2]
				},
				fields=['name']
			)
			if existing:
				link = frappe.utils.get_link_to_form('Monthly Implementation Summery', existing[0].name)
				implementation_link = frappe.utils.get_link_to_form('Implementation', self.implementation)
				frappe.throw(
					f"A Monthly Implementation Summery record {link} already exists for "
					f"Implementation {implementation_link}, Year {self.year} and Month {self.month}."
				)

	def _recalculate_totals_from_timesheets_table(self):
		"""Recalculate total_hours and billable_hours from timesheets_table."""
		if not self.timesheets_table:
			return
		self.total_hours = flt(sum(flt(row.total_hours) for row in self.timesheets_table), precision=2)
		self.billable_hours = flt(sum(flt(row.billable_hours) for row in self.timesheets_table), precision=2)

	def set_timesheets_table(self):
		"""Fetch timesheets for the previous month and populate child table."""
		prev_year, prev_month_name = _get_previous_month_year_and_name(self.year, self.month)
		if not prev_year or not prev_month_name:
			self.timesheets_table = []
			return
		
		from_date, to_date = _get_month_date_range(prev_year, prev_month_name)
		if not from_date or not to_date:
			self.timesheets_table = []
			return

		projects = frappe.get_all(
			"Project",
			filters={"custom_implementation": self.implementation},
			pluck="name"
		)
		if not projects:
			self.timesheets_table = []
			return

		Timesheet = DocType("Timesheet")
		TimesheetDetail = DocType("Timesheet Detail")
		Employee = DocType("Employee")

		query = (
			frappe.qb.from_(Timesheet)
			.inner_join(TimesheetDetail)
			.on(TimesheetDetail.parent == Timesheet.name)
			.inner_join(Employee)
			.on(Employee.name == Timesheet.employee)
			.select(
				Timesheet.name.as_("ts_name"),
				Timesheet.start_date.as_("date"),
				Timesheet.total_hours,
				Timesheet.total_billable_hours,
				Timesheet.custom_rating.as_("rating"),
				TimesheetDetail.project.as_("project"),
				Timesheet.employee,
				Employee.employee_name.as_("employee_name"),
				Timesheet.note.as_("description"),
			)
			.where(TimesheetDetail.project.isin(projects))
			.where(Timesheet.docstatus != 2)
			.where(Timesheet.start_date.between(from_date, to_date))
			.orderby(Employee.employee_name, order=Order.asc)
			.orderby(Timesheet.total_billable_hours, order=Order.desc)
		)
		timesheet_list = query.run(as_dict=True)

		# Populate child table (totals recalculated in _recalculate_totals_from_timesheets_table)
		self.timesheets_table = []
		for row in timesheet_list:
			self.append("timesheets_table", {
			"timesheet": row.ts_name or None,
			"date": row.date,
			"total_hours": flt(row.total_hours),
			"billable_hours": flt(row.billable_hours),
			"rating": row.rating or "",
			"project": row.project or None,
			"employee": row.employee or None,
			"employee_name": row.employee_name or "",
			"description": row.description or ""
		})

	
def _get_item_selling_rate(item_code, uom=None):
	"""Fetch price_list_rate from Item Price where selling=1. Prefer UOM match if specified."""
	filters = {"item_code": item_code, "selling": 1}
	if uom:
		filters["uom"] = uom
	rate = frappe.db.get_value(
		"Item Price",
		filters,
		"price_list_rate",
		order_by="valid_from desc",
	)
	if rate is not None:
		return flt(rate, 2)
	# Fallback: try without UOM filter (stock UOM or first match)
	if uom:
		rate = frappe.db.get_value(
			"Item Price",
			{"item_code": item_code, "selling": 1},
			"price_list_rate",
			order_by="valid_from desc",
		)
	return flt(rate, 2) if rate is not None else 0


def _get_previous_month_year_and_name(year_str, month_name):
	"""Return (year, month_name) for previous month. Returns (None, None) if invalid."""
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
	else:
		month_names = list(MONTH_NAME_TO_NUM.keys())
		return str(year_int), month_names[month_num - 2]


def _get_month_date_range(year_str, month_name):
	"""Return (first_day, last_day) of month. Returns (None, None) if invalid."""
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


@frappe.whitelist()
def create_delivery_note(docname: str, sales_order=None, delivery_note_item=None):
	"""Create DN from sales_order if given, else from timesheets. Append rows to mis-dni with ref_doc=dn_name.

	DN is NOT updated here. submit_mis_dn_action runs on MIS submit (update or create DN from mis-dni).
	"""
	if not docname:
		raise frappe.ValidationError("docname is required")

	if sales_order:
		dn_name = _create_dn_from_sales_order(docname, sales_order, delivery_note_item)
	else:
		doc = frappe.get_doc("Monthly Implementation Summery", docname)
		old_dn = doc.delivery_note
		dn_name = doc._create_dn_from_timesheets()
		update_dn_table_in_summary(docname, dn_name, old_dn=old_dn)

	return {"status": "ok", "dn_name": dn_name}


def _create_dn_from_sales_order(docname, sales_order, delivery_note_item=None):
	"""Create DN from Sales Order, sync to mis-dni."""
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


def _serialize_row(r):
	"""Convert form row (dict or object) to dict for delivery_note_item."""
	d = r if isinstance(r, dict) else (r.as_dict() if hasattr(r, "as_dict") else {})
	fields = ("item_code", "item_name", "item_group", "qty", "stock_uom", "uom",
		"conversion_factor", "rate", "amount", "expense_account", "cost_center", "custom_ref_doc")
	return {k: d[k] for k in fields if k in d}


def update_dn_table_in_summary(docname, dn_name, old_dn=None, existing_rows=None):
	"""Sync DN items to mis-dni. Remove rows where ref_doc is linked to delivery note (old or new DN). Add new DN rows. Never touch ref_doc=mis_name."""
	if not docname or not dn_name:
		return
	dn_doc = frappe.get_doc("Delivery Note", dn_name)
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.reload()

	# Remove rows where ref_doc = linked delivery note (old DN or current dn_name)
	dn_refs_to_remove = {dn_name}
	if old_dn:
		dn_refs_to_remove.add(old_dn)
	doc.delivery_note_item = [
		r for r in (doc.delivery_note_item or [])
		if getattr(r, "custom_ref_doc", None) not in dn_refs_to_remove
	]

	# Append new rows from DN with ref_doc=dn_name (preserve against_sales_order + so_detail for SO linkage)
	for item in dn_doc.items:
		rate = flt(item.rate, 2)
		if rate <= 0:
			rate = _get_item_selling_rate(item.item_code, uom=item.uom)
			amount = flt(rate * item.qty, 2)
		else:
			amount = item.amount
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
	"""Update mis-dni from current timesheets_table. Does NOT update the DN.

	DN is updated only when MIS is submitted. Called by 'Update current timesheets hours' button.
	"""
	if not docname:
		raise frappe.ValidationError("docname is required")

	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.update_mis_delivery_note_item_from_timesheets(existing_rows=delivery_note_item)
	return {"status": "ok", "message": frappe._("Delivery Note Items updated from current timesheets.")}


@frappe.whitelist()
def submit_mis_dn_action(docname: str):
	"""On MIS submit: update DN with mis-dni rows if DN exists, else create DN from mis-dni."""
	if not docname:
		raise frappe.ValidationError("docname is required")
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.reload()
	dn_name = doc._get_linked_dn_name()
	if dn_name:
		doc.update_delivery_note_from_mis_items()
	else:
		doc._create_dn_from_mis_dni()
	return {"status": "ok"}


@frappe.whitelist()
def update_dn_from_mis_items(docname: str):
	"""Update DN from mis-dni. Called on MIS submit when DN exists."""
	if not docname:
		raise frappe.ValidationError("docname is required")
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.update_delivery_note_from_mis_items()
	return {"status": "ok"}


@frappe.whitelist()
def create_dn_from_mis_dni(docname: str):
	"""Create DN from mis-dni. Called on MIS submit when no DN exists."""
	if not docname:
		raise frappe.ValidationError("docname is required")
	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc._create_dn_from_mis_dni()
	return {"status": "ok"}


def get_items_for_delivery_note(docname,so):
        items = []
        dn_items = []
        if so:
            so_doc = frappe.get_doc("Sales Order", so).load_from_db()
            for so_item in so_doc.items:
                dn_item = frappe.get_doc({
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
                    "so_detail": so_item.name
                })
                dn_items.append(dn_item)

        return dn_items

