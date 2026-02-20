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
	
	# Only execute on the 1st of the month
	if today_date.day != 1:
		return
	
	# Calculate previous month
	if today_date.month == 1:
		prev_month_num = 12
		prev_year = today_date.year - 1
	else:
		prev_month_num = today_date.month - 1
		prev_year = today_date.year
	
	# Month names
	month_names = [
		"January", "February", "March", "April", "May", "June",
		"July", "August", "September", "October", "November", "December"
	]
	prev_month_name = month_names[prev_month_num - 1]
	
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
			# Check if Monthly Implementation Summary already exists
			existing = frappe.db.exists(
				"Monthly Implementation Summery",
				{
					"implementation": impl.name,
					"year": str(prev_year),
					"month": prev_month_name
				}
			)
			
			if existing:
				skipped_count += 1
				continue
			
			# Create new Monthly Implementation Summary
			doc = frappe.get_doc({
				"doctype": "Monthly Implementation Summery",
				"implementation": impl.name,
				"year": str(prev_year),
				"month": prev_month_name,
				"discount": 0
			})
			doc.insert()
			
			# Refresh timesheets (this will auto-populate via validate method)
			doc.refresh_timesheets()
			doc.save()
			
			created_count += 1
			frappe.db.commit()
			
		except Exception as e:
			error_count += 1
			frappe.log_error(
				f"Error creating Monthly Implementation Summary for {impl.name}: {str(e)}",
				"create_monthly_implementation_summaries"
			)
			frappe.db.rollback()
	
	# Log results
	frappe.logger().info(
		f"Monthly Implementation Summary creation completed: "
		f"Created: {created_count}, Skipped: {skipped_count}, Errors: {error_count}"
	)
