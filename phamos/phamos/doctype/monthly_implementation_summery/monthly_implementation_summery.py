# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, get_url, formatdate
from datetime import datetime
from calendar import monthrange


class MonthlyImplementationSummery(Document):
	def validate(self):
		"""Auto-refresh timesheets when Implementation, Year, and Month are set"""
		if self.implementation and self.year and self.month:
			if not self.is_new():
				self.refresh_timesheets()
			self.calculate_totals()
	
	def refresh_timesheets(self):
		"""Fetch and populate timesheets for the implementation and month"""
		timesheets_data = self.get_timesheets_for_month()
		
		if timesheets_data:
			# Format timesheets as HTML table
			html_content = self.format_timesheets_html(timesheets_data)
			self.timesheets = html_content
			
			# Calculate totals
			self.calculate_totals()
		else:
			self.timesheets = ""
			self.total_hours = 0
			self.billable_hours = 0
	
	def get_timesheets_for_month(self):
		"""Query draft timesheets for the implementation and month"""
		if not (self.implementation and self.year and self.month):
			return []
		
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
			fields=["name"]
		)
		
		if not projects:
			return []
		
		project_names = [p.name for p in projects]
		
		# Query timesheets via Timesheet Detail
		timesheets = frappe.db.sql("""
			SELECT DISTINCT
				ts.name,
				ts.start_date,
				ts.end_date,
				ts.total_hours,
				ts.total_billable_hours,
				ts.custom_rating,
				ts.employee,
				ts.project_name
			FROM `tabTimesheet` ts
			INNER JOIN `tabTimesheet Detail` tsd ON tsd.parent = ts.name
			WHERE ts.docstatus = 0
				AND tsd.project IN %(projects)s
				AND (
					(ts.start_date <= %(last_day)s AND ts.end_date >= %(first_day)s)
					OR (ts.start_date BETWEEN %(first_day)s AND %(last_day)s)
					OR (ts.end_date BETWEEN %(first_day)s AND %(last_day)s)
				)
			ORDER BY ts.start_date DESC, ts.creation DESC
		""", {
			"projects": project_names,
			"first_day": first_day,
			"last_day": last_day
		}, as_dict=True)
		
		return timesheets
	
	def format_timesheets_html(self, timesheets_data):
		"""Format timesheets data as HTML table"""
		if not timesheets_data:
			return ""
		
		html = """
		<div class="overflow-auto">
		<table class="table table-bordered table-condensed table-hover">
		<thead><tr>
		<th>Timesheet</th><th>Date</th><th>Total Hours</th><th>Billable Hours</th><th>Rating</th>
		</tr></thead>
		<tbody>
		"""
		
		for ts in timesheets_data:
			timesheet_url = get_url(f"/app/timesheet/{ts.name}")
			date_str = formatdate(ts.start_date, "dd.MM.yyyy") if ts.start_date else ""
			rating = ts.custom_rating or ""
			
			html += f"""
			<tr>
				<td><a href="{timesheet_url}" target="_blank">{ts.name}</a></td>
				<td>{date_str}</td>
				<td>{frappe.format_value(ts.total_hours or 0, {'fieldtype': 'Float'})}</td>
				<td>{frappe.format_value(ts.total_billable_hours or 0, {'fieldtype': 'Float'})}</td>
				<td>{rating}</td>
			</tr>
			"""
		
		html += """
		</tbody>
		</table>
		</div>
		"""
		
		return html
	
	def calculate_totals(self):
		"""Calculate total hours, billable hours, and total after discount"""
		if not self.timesheets:
			self.total_hours = 0
			self.billable_hours = 0
			self.total_hours_after_discount = 0
			return
		
		# Get timesheets data to calculate totals
		timesheets_data = self.get_timesheets_for_month()
		
		if timesheets_data:
			# Sum up totals (group by timesheet to avoid duplicates)
			seen_timesheets = set()
			total_hours = 0
			billable_hours = 0
			
			for ts in timesheets_data:
				if ts.name not in seen_timesheets:
					seen_timesheets.add(ts.name)
					total_hours += ts.total_hours or 0
					billable_hours += ts.total_billable_hours or 0
			
			self.total_hours = total_hours
			self.billable_hours = billable_hours
		else:
			self.total_hours = 0
			self.billable_hours = 0
		
		# Calculate total hours after discount
		discount_pct = self.discount or 0
		if discount_pct > 0:
			discount_amount = (self.billable_hours * discount_pct) / 100
			self.total_hours_after_discount = self.billable_hours - discount_amount
		else:
			self.total_hours_after_discount = self.billable_hours
	
	@frappe.whitelist()
	def refresh_timesheets_api(self):
		"""API endpoint to refresh timesheets from client-side"""
		self.refresh_timesheets()
		self.save()
		
		return {
			"timesheets_count": len(self.get_timesheets_for_month()),
			"total_hours": self.total_hours,
			"billable_hours": self.billable_hours,
			"total_hours_after_discount": self.total_hours_after_discount
		}
