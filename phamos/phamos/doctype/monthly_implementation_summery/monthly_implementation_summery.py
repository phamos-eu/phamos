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

	def on_submit(self):
		self.validate_phamos_settings_item()
		self.validate_timesheet_hours_for_delivery_note()
		# Create Delivery Note when Monthly Implementation Summary is submitted
		if self.implementation and self.year and self.month:
			try:
				item = frappe.db.get_single_value("phamos Settings", "item")
				if not item:
					frappe.throw("No item configured in Phamos Settings. Please set an item to create Delivery Note.")
				# Use total_hours_after_discount if discount is applied, otherwise use billable_hours
				if self.total_hours_after_discount is not None and self.total_hours_after_discount > 0:
					total_billing_hours = flt(self.total_hours_after_discount)
				else:
					total_billing_hours = flt(self.billable_hours or 0)
				if total_billing_hours <= 0:
					frappe.throw("Total billing hours is zero or empty. Delivery Note cannot be created.")
				impl = frappe.get_cached_doc("Implementation", self.implementation)
				customer = impl.get("customer")
				if not customer:
					frappe.throw("Implementation has no Customer. Set Customer on Implementation to create Delivery Note.")
				company = frappe.db.get_default("company") or frappe.db.get_value("Customer", customer, "customer_primary_company")
				if not company:
					company = frappe.db.get_single_value("Global Defaults", "default_company")
				if not company:
					frappe.throw("No Company set. Set default Company in Global Defaults or for the Customer.")
				dn = frappe.get_doc({
					"doctype": "Delivery Note",
					"customer": customer,	
					"company": company,
					"custom_implementation": self.implementation,
					"docstatus": 0,  # Insert as submitted
				})
				dn.append("items", {
					"item_code": item,
					"qty": total_billing_hours,
					"uom": "Hour",
					"allow_zero_valuation_rate": 1,
					"custom_against_monthly_implementation_summery": self.name,
				})
				dn.insert()
				formatted_hours = frappe.format_value(total_billing_hours, {"fieldtype": "Float"}, doc=None)
				frappe.msgprint(f"Delivery Note {dn.name} created successfully with {formatted_hours} Hour(s).")

			except Exception as e:
				frappe.msgprint(f"Error creating Delivery Note : {str(e)}")		

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
		"""Fetch timesheets for the previous month of the selected year and month and set HTML table."""
		# Calculate previous month from selected year and month
		prev_year, prev_month_name = _get_previous_month_year_and_name(self.year, self.month)
		if not prev_year or not prev_month_name:
			self.timesheets = ""
			return
		
		from_date, to_date = _get_month_date_range(prev_year, prev_month_name)
		if not from_date or not to_date:
			self.timesheets = ""
			return

		projects = frappe.get_all(
			"Project",
			filters={"custom_implementation": self.implementation},
			pluck="name",
		)
		if not projects:
			self.timesheets = ""
			return

		timesheet_list = frappe.db.sql("""
			SELECT DISTINCT ts.name AS ts_name,
				ts.start_date AS date,
				ts.total_hours AS total_hours,
				ts.total_billable_hours AS billable_hours,
				ts.custom_rating AS rating,
				tsd.project AS project
			FROM `tabTimesheet` ts
			INNER JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
			WHERE tsd.project IN %(projects)s
				AND ts.docstatus != 2
				AND ts.start_date BETWEEN %(from_date)s AND %(to_date)s
			ORDER BY ts.start_date DESC, ts.name DESC
		""", {
			"projects": projects,
			"from_date": from_date,
			"to_date": to_date,
		}, as_dict=True)

		# Calculate sums - since we use DISTINCT on ts.name, each timesheet appears only once
		# So we can safely sum the total_hours and billable_hours
		total_hours_sum = sum(flt(row.total_hours or 0) for row in timesheet_list)
		billable_hours_sum = sum(flt(row.billable_hours or 0) for row in timesheet_list)
		self.total_hours = flt(total_hours_sum, precision=2)
		# Store original billable hours (before discount) - will be used by apply_discount_to_billing_hours
		self.billable_hours = flt(billable_hours_sum, precision=2)
		self.timesheets = _build_timesheets_html(timesheet_list)

	def apply_discount_to_billing_hours(self):
		"""Apply discount percentage to billable hours if discount is set."""
		# Use the billable_hours field value (which was set in set_timesheets_table)
		# This ensures we always apply discount to the original value
		original_billable_hours = flt(self.billable_hours or 0)
		
		if original_billable_hours > 0:
			if self.discount:
				discount_percent = flt(self.discount)
				# Validate discount is between 0 and 100
				if discount_percent < 0:
					frappe.throw("Discount cannot be negative.")
				if discount_percent > 100:
					frappe.throw("Discount cannot exceed 100%.")
				if discount_percent > 0:
					# Apply discount: discounted_hours = original_billable_hours * (1 - discount/100)
					discounted_hours = original_billable_hours * (1 - discount_percent / 100)
					self.total_hours_after_discount = flt(discounted_hours, precision=2)
				else:
					# No discount, use original value
					self.total_hours_after_discount = original_billable_hours
			else:
				# No discount set, use original value
				self.total_hours_after_discount = original_billable_hours
		else:
			# No billable hours, set to 0
			self.total_hours_after_discount = 0

	def _get_original_billable_hours(self):
		"""Get original billable hours from timesheets (before discount)."""
		if not (self.implementation and self.year and self.month):
			return None
		
		# Convert month name to number
		month_names = [
			"January", "February", "March", "April", "May", "June",
			"July", "August", "September", "October", "November", "December"
		]
		try:
			month_num = month_names.index(self.month) + 1
		except ValueError:
			frappe.throw(f"Invalid month: {self.month}")
		
		# Get date range: from January 1st of the year to the last day of selected month
		year_int = int(self.year)
		# Start from January 1st of the selected year
		first_day = datetime(year_int, 1, 1).date()
		# End at the last day of the selected month
		last_day_num = monthrange(year_int, month_num)[1]
		last_day = datetime(year_int, month_num, last_day_num).date()
		
		# Get all projects linked to this implementation
		projects = frappe.get_all(
			"Project",
			filters={"custom_implementation": self.implementation},
			pluck="name",
		)
		if not projects:
			return None

		# Use DISTINCT on timesheet name to avoid double-counting when a timesheet has multiple projects
		# Then sum the total_billable_hours (which is already the total for each timesheet)
		timesheet_list = frappe.db.sql("""
			SELECT DISTINCT ts.name AS ts_name,
				ts.total_billable_hours AS billable_hours
			FROM `tabTimesheet` ts
			INNER JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
			WHERE tsd.project IN %(projects)s
				AND ts.docstatus != 2
				AND ts.start_date BETWEEN %(from_date)s AND %(to_date)s
		""", {
			"projects": projects,
			"from_date": from_date,
			"to_date": to_date,
		}, as_dict=True)

		billable_hours_sum = sum(flt(row.billable_hours or 0) for row in timesheet_list)
		return billable_hours_sum


def _get_previous_month_year_and_name(year_str, month_name):
	"""Given year (YYYY string) and month name (e.g. January), return (prev_year_str, prev_month_name) for the previous month.
	Returns (None, None) if invalid.
	Example: (2026, "January") -> (2025, "December")
	Example: (2026, "March") -> (2026, "February")
	"""
	if not year_str or not month_name:
		return None, None
	month_num = MONTH_NAME_TO_NUM.get(month_name)
	if not month_num:
		return None, None
	try:
		year_int = int(str(year_str).strip())
	except (ValueError, TypeError):
		return None, None
	
	# Calculate previous month
	if month_num == 1:
		# January -> December of previous year
		prev_year_int = year_int - 1
		prev_month_name = "December"
	else:
		# Other months -> previous month of same year
		prev_year_int = year_int
		month_names = list(MONTH_NAME_TO_NUM.keys())
		prev_month_name = month_names[month_num - 2]  # month_num - 2 because list is 0-indexed
	
	return str(prev_year_int), prev_month_name


def _get_month_date_range(year_str, month_name):
	"""Given year (YYYY string) and month name (e.g. January), return (first_day, last_day) of that month. Returns (None, None) if invalid."""
	if not year_str or not month_name:
		return None, None
	month_num = MONTH_NAME_TO_NUM.get(month_name)
	if not month_num:
		return None, None
	try:
		year_int = int(str(year_str).strip())
	except (ValueError, TypeError):
		return None, None
	first_day = get_first_day(f"{year_int}-{month_num:02d}-01")
	last_day = get_last_day(first_day)
	return first_day, last_day


def _build_timesheets_html(timesheet_list):
	"""Build HTML table: TS name, Date, Total Hours, Billable Hours, Rating (no Action)."""
	if not timesheet_list:
		return "<p>No timesheets found for the previous month.</p>"

	rows = []
	for row in timesheet_list:
		date_str = formatdate(row.date) if row.date else ""
		total_hrs = frappe.format_value(row.total_hours, df={"fieldtype": "Float"}, doc=None) if row.total_hours is not None else "0"
		billable_hrs = frappe.format_value(row.billable_hours, df={"fieldtype": "Float"}, doc=None) if row.billable_hours is not None else "0"
		rating = row.rating or ""
		project = str(row.project or "") if row.project else ""
		
		# Make timesheet name clickable
		ts_name = str(row.ts_name or "")
		ts_link = ""
		if ts_name:
			ts_url = get_url_to_form("Timesheet", ts_name)
			ts_link = f'<a href="{escape_html(ts_url)}" target="_blank">{escape_html(ts_name)}</a>'
		
		# Make project name clickable
		project_link = ""
		if project:
			project_url = get_url_to_form("Project", project)
			project_link = f'<a href="{escape_html(project_url)}" target="_blank">{escape_html(project)}</a>'
		
		rows.append(
			f"<tr><td>{ts_link}</td>"
			f"<td>{escape_html(date_str)}</td>"
			f"<td>{escape_html(str(total_hrs))}</td>"
			f"<td>{escape_html(str(billable_hrs))}</td>"
			f"<td>{escape_html(str(rating))}</td>"
			f"<td>{project_link}</td></tr>"
		)

	table_body = "\n".join(rows)
	html = f"""<div class="overflow-auto">
<table class="table table-bordered table-condensed table-hover">
<thead><tr>
<th>Timesheet</th><th>Date</th><th>Total Hours</th><th>Billable Hours</th><th>Rating</th><th>Project</th>
</tr></thead>
<tbody>
{table_body}
</tbody>
</table>
</div>"""
	return html




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