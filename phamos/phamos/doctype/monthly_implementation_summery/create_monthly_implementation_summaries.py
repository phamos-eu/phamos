# Copyright (c) 2026, phamos.eu and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import today, getdate
from datetime import datetime, timedelta
from calendar import monthrange


def create_monthly_implementation_summaries():
	"""
	Automatically create Monthly Implementation Summary documents
	on the 1st of each month for the previous month.
	Runs daily but only executes on the 1st of the month.
	"""
	today_date = getdate(today())
	
	# Only execute on the configured day of the month
	day = 1
	day = int(day)  # ensure integer (DB may return string)
	if today_date.day != day:
		return
	
	# Use current year and current month for the document
	# (Timesheets will be fetched for previous months by the doctype logic)
	month_names = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December"
	]
	current_year = today_date.year
	current_month_name = month_names[today_date.month - 1]
	
	# Get all active Implementations
	implementations = frappe.get_all(
		"Implementation",
		filters={"status": "Open"},
		fields=["name"]
	)
	
	created_count = 0
	skipped_count = 0
	error_count = 0
	
	for impl in implementations:
		try:
			# Check if Monthly Implementation Summary already exists for current year + current month
			existing = frappe.db.exists(
				"Monthly Implementation Summery",
				{
					"implementation": impl.name,
					"year": str(current_year),
					"month": current_month_name,
					"docstatus": ["in", [0, 1]]
				}
			)
			
			if existing:
				skipped_count += 1
				continue
			
			# Create new Monthly Implementation Summary (year=current year, month=current month)
			# Doctype validate() will fetch timesheets for the previous month(s)
			doc = frappe.get_doc({
				"doctype": "Monthly Implementation Summery",
				"implementation": impl.name,
				"year": str(current_year),
				"month": current_month_name,
				"discount": 0
			})
			doc.insert()
			
			created_count += 1
			frappe.db.commit()
			
		except Exception:
			error_count += 1
			frappe.db.rollback()
	
