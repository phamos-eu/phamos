# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_first_day, get_last_day, formatdate, escape_html, get_url_to_form, flt
from frappe.utils import today, getdate, add_months, formatdate
from datetime import datetime

from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice

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
		if self.implementation and self.year and self.month:
			self.set_timesheets_table()
			self.apply_discount_to_billing_hours()
			#self.validate_phamos_settings_item()

	def validate_phamos_settings_item(self):
		"""Block save/submit if Phamos Settings has no default item (required for Delivery Note)."""
		item = frappe.db.get_single_value("phamos Settings", "item")
		if not item:
			frappe.throw(
				"No item configured in Phamos Settings. Please set the default Item in Phamos Settings (Monthly Implementation Summery tab) before submitting."
			)

	def validate_timesheet_hours_for_delivery_note(self):
		"""Block submit if total billable hours (after discount) is zero or empty, as Delivery Note cannot be created."""
		# Check total_hours_after_discount if discount is applied, otherwise check billable_hours
		if self.total_hours_after_discount is not None and self.total_hours_after_discount > 0:
			hours_to_check = flt(self.total_hours_after_discount)
		else:
			hours_to_check = flt(self.billable_hours or 0)
		
		if hours_to_check <= 0:
			frappe.throw(
				"Total billable hours (after discount) is zero or empty. Please ensure there are billable hours before submitting, as a Delivery Note will be created."
			)

	def create_delivery_note(self):
		"""Create Delivery Note on submit."""
		try:
			self.validate_phamos_settings_item()
			self.validate_timesheet_hours_for_delivery_note()
			
			# Get billing hours
			total_billing_hours = flt(self.total_hours_after_discount or self.billable_hours)
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
			
			
		except Exception as e:
			frappe.log_error(f"Error creating Delivery Note for {self.name}: {str(e)}")
			frappe.throw(f"Error creating Delivery Note: {str(e)}")		

	def update_delivery_note(self):	
		"""Update existing Delivery Note on submit if it already exists."""
		try:
			self.validate_phamos_settings_item()
			self.validate_timesheet_hours_for_delivery_note()
			# Prefer explicit link; if missing, try to find by custom_against_monthly_implementation_summery
			dn_name = self.delivery_note
			if not dn_name:
				dn_name = frappe.db.get_value(
					"Delivery Note",
					{
						"custom_against_monthly_implementation_summery": self.name,
						"docstatus": ["!=", 2],
					},
					"name",
				)
				if not dn_name:
					frappe.throw("No Delivery Note linked to this Monthly Implementation Summery.")
				# Keep the link field in sync for future calls
				self.delivery_note = dn_name
				self.db_set("delivery_note", dn_name)

			dn = frappe.get_doc("Delivery Note", dn_name)
			if dn.docstatus == 2:
				frappe.throw("Cannot update Delivery Note as it is cancelled.")
			
			# Update item quantity based on total billing hours
			total_billing_hours = flt(self.total_hours_after_discount or self.billable_hours)
			if total_billing_hours <= 0:
				frappe.throw("Total billing hours is zero. Delivery Note cannot be updated.")
			
			item = frappe.db.get_single_value("phamos Settings", "item")
			if not item:
				frappe.throw("No item configured in Phamos Settings.")

			# Replace items table with a single row reflecting the new total hours
			
			dn.append("items", {
				"item_code": item,
				"qty": total_billing_hours,
				"uom": "Hour",
				"allow_zero_valuation_rate": 1,
				"custom_against_monthly_implementation_summery": self.name,
			})
			dn.save()
			frappe.msgprint(f"Delivery Note {dn.name} updated with {total_billing_hours:.2f} Hour(s).")
			
		except Exception as e:
			frappe.log_error(f"Error updating Delivery Note for {self.name}: {str(e)}")
			frappe.throw(f"Error updating Delivery Note: {str(e)}")		

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

		timesheet_list = frappe.db.sql("""
			SELECT DISTINCT ts.name AS ts_name,
				ts.start_date AS date,
				ts.total_hours AS total_hours,
				ts.total_billable_hours AS billable_hours,
				ts.custom_rating AS rating,
				tsd.project AS project,
				ts.employee AS employee,
				ts.note AS description
			FROM `tabTimesheet` ts
			INNER JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
			WHERE tsd.project IN %(projects)s
				AND ts.docstatus != 2
				AND ts.start_date BETWEEN %(from_date)s AND %(to_date)s
			ORDER BY ts.start_date DESC, ts.name DESC
		""", {
			"projects": projects,
			"from_date": from_date,
			"to_date": to_date
		}, as_dict=True)

		# Calculate totals
		self.total_hours = flt(sum(flt(row.total_hours) for row in timesheet_list), precision=2)
		self.billable_hours = flt(sum(flt(row.billable_hours) for row in timesheet_list), precision=2)
		
		# Populate child table
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
			"description": row.description or ""
		})

	def apply_discount_to_billing_hours(self):
		"""Apply discount percentage to billable hours."""
		original_billable_hours = flt(self.billable_hours)
		discount_percent = flt(self.discount)
		
		# Validate discount
		if discount_percent < 0:
			frappe.throw("Discount cannot be negative.")
		if discount_percent > 100:
			frappe.throw("Discount cannot exceed 100%.")
		
		# Calculate discounted hours
		if discount_percent > 0 and original_billable_hours > 0:
			self.total_hours_after_discount = flt(
				original_billable_hours * (1 - discount_percent / 100), 
				precision=2
			)
		else:
			self.total_hours_after_discount = original_billable_hours

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
def create_delivery_note_from_summary(docname: str):
	"""Create a Delivery Note based on the Monthly Implementation Summery's timesheet hours.

	This is a thin RPC wrapper that loads the document and calls its existing
	`create_delivery_note` document method.
	"""
	if not docname:
		raise frappe.ValidationError("docname is required")

	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.create_delivery_note()

	# We don't rely on the return value on the client; status is enough.
	return {"status": "ok"}


@frappe.whitelist()
def update_delivery_note_from_summary(docname: str):
	"""Update the existing Delivery Note linked to the Monthly Implementation Summery.

	This is a thin RPC wrapper that loads the document and calls its existing
	`update_delivery_note` document method.
	"""
	if not docname:
		raise frappe.ValidationError("docname is required")

	doc = frappe.get_doc("Monthly Implementation Summery", docname)
	doc.update_delivery_note()

	return {"status": "ok"}


"""
Scheduled job to create Monthly Implementation Summery documents on the 1st of each month
for all active Implementations.
"""

def create_monthly_deliveries():
	"""
	Create Monthly Implementation Summery documents for the previous month for all active Implementations.
	This function should be called daily via scheduler, but will only create documents on the 1st of each month.
	"""
	today_date = getdate(today())

	# Only run on the 1st of each month
	if today_date.day != 1:
		return

	# Previous month: year (4-digit string) and month name
	previous_month_date = add_months(today_date, -1)
	previous_year = str(previous_month_date.year)
	# Month name for Select field (January, February, ...)
	month_names = list(MONTH_NAME_TO_NUM.keys())
	previous_month_name = month_names[previous_month_date.month - 1]

	frappe.logger().info(
		f"Creating Monthly Implementation Summeries for year: {previous_year}, month: {previous_month_name}"
	)

	active_implementations = frappe.get_all(
		'Implementation',
		filters={'status': 'Open'},
		fields=['name']
	)

	created_count = 0
	skipped_count = 0

	for impl in active_implementations:
		implementation_name = impl.name

		existing = frappe.db.exists('Monthly Implementation Summery', {
			'implementation': implementation_name,
			'year': previous_year,
			'month': previous_month_name,
		})

		if existing:
			frappe.logger().info(
				f"Monthly Implementation Summery already exists for Implementation {implementation_name}, "
				f"year {previous_year}, month {previous_month_name}"
			)
			skipped_count += 1
			continue

		try:
			doc = frappe.get_doc({
				'doctype': 'Monthly Implementation Summery',
				'implementation': implementation_name,
				'year': previous_year,
				'month': previous_month_name,
			})
			doc.insert()
			frappe.db.commit()

			created_count += 1
			frappe.logger().info(
				f"Created Monthly Implementation Summery {doc.name} for Implementation {implementation_name}, "
				f"year {previous_year}, month {previous_month_name}"
			)
		except Exception as e:
			frappe.logger().error(
				f"Error creating Monthly Implementation Summery for Implementation {implementation_name}, "
				f"year {previous_year}, month {previous_month_name}: {str(e)}"
			)
			frappe.db.rollback()

	frappe.logger().info(
		f"Monthly Implementation Summery creation completed. Created: {created_count}, Skipped: {skipped_count}"
	)

	return {
		'created': created_count,
		'skipped': skipped_count,
		'year': previous_year,
		'month': previous_month_name,
	}

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
                    "so_detail": so_item.name,
					"custom_against_monthly_implementation_summery": docname
                })
                dn_items.append(dn_item)

        return dn_items

@frappe.whitelist()
def create_delivery_note(docname, sales_order):
	"""Create Delivery Note from Sales Order."""
	try:
		if not sales_order:
			return {"error": "No Sales Order found."}
		
		items = get_items_for_delivery_note(docname, sales_order)
		if not items:
			return None
		
		so_doc = frappe.get_doc("Sales Order", sales_order)
		selling_price_list = so_doc.selling_price_list
		
		dn = frappe.get_doc({
			"doctype": "Delivery Note",
			"customer": so_doc.customer,
			"project": so_doc.project,
			"palette": 0,
			"paket": 0,
			"items": items,
			"custom_proma_checklist_data": docname,
			"docstatus": 0,
			"posting_date": frappe.utils.nowdate(),
			"selling_price_list": selling_price_list,
		})
		dn.insert()
		frappe.db.set_value("Monthly Implementation Summery", docname, "delivery_note", dn.name)
		frappe.db.commit()
		return dn.name
	except Exception as e:
		frappe.log_error(f"Error creating DN for {docname}: {str(e)}")
		return None
		