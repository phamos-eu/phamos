import frappe
from frappe.utils import flt


def execute():
	"""
	Patch to fix timesheets for MIS-August-0008.
	Reads timesheets from the MIS table, finds the underlying Timesheet Record that created
	each timesheet, and updates the timesheet hours/times as if the Timesheet Record is being
	submitted for the first time.
	Updates:
	- Timesheet time_logs: from_time, to_time, hours (from actual_time / 3600), billing_hours
	- Timesheet: total_hours, total_billable_hours
	- MIS timesheets_table: total_hours, billable_hours
	"""

	mis_name = "MIS-August-0008"

	if not frappe.db.exists("Monthly Implementation Summary", mis_name):
		frappe.logger().info(f"[fix_mis_august_0008_timesheets] {mis_name} not found, skipping patch.")
		return

	mis = frappe.get_doc("Monthly Implementation Summary", mis_name)

	updated_count = 0
	skipped_timesheets = []

	for ts_row in (mis.timesheets_table or []):
		if not ts_row.timesheet:
			continue

		timesheet_name = ts_row.timesheet

		timesheet_record = frappe.db.get_value(
			"Timesheet Record",
			{"timesheet": timesheet_name},
			["name", "from_time", "to_time", "actual_time", "percent_billable"],
			as_dict=True
		)

		if not timesheet_record:
			skipped_timesheets.append(f"{timesheet_name}: No matching Timesheet Record found")
			continue

		try:
			ts_doc = frappe.get_doc("Timesheet", timesheet_name)
		except Exception as e:
			skipped_timesheets.append(f"{timesheet_name}: Error loading Timesheet - {str(e)}")
			continue

		if ts_doc.docstatus == 2:
			skipped_timesheets.append(f"{timesheet_name}: Timesheet is cancelled (docstatus=2)")
			continue

		if ts_doc.time_logs and len(ts_doc.time_logs) > 1:
			skipped_timesheets.append(
				f"{timesheet_name}: Has {len(ts_doc.time_logs)} time_logs - "
				f"skipping to avoid incorrect totals (expected exactly 1)"
			)
			continue

		actual_hours = flt(timesheet_record.actual_time) / 3600 if timesheet_record.actual_time else 0
		actual_hours = round(actual_hours, 6)

		percent_billable = flt(timesheet_record.percent_billable) if timesheet_record.percent_billable else 0
		billing_hours = actual_hours * (percent_billable / 100) if percent_billable > 0 else 0
		billing_hours = round(billing_hours, 6)

		from_time = timesheet_record.from_time
		to_time = timesheet_record.to_time

		if not ts_doc.time_logs:
			ts_doc.append("time_logs", {
				"from_time": from_time,
				"to_time": to_time,
				"hours": actual_hours,
				"billing_hours": billing_hours,
				"is_billable": 1 if percent_billable > 0 else 0,
			})
		else:
			ts_doc.time_logs[0].from_time = from_time
			ts_doc.time_logs[0].to_time = to_time
			ts_doc.time_logs[0].hours = actual_hours
			ts_doc.time_logs[0].billing_hours = billing_hours
			ts_doc.time_logs[0].is_billable = 1 if percent_billable > 0 else 0

		ts_doc.total_hours = round(sum(flt(log.hours) for log in ts_doc.time_logs), 2)
		ts_doc.total_billable_hours = round(sum(flt(log.billing_hours) for log in ts_doc.time_logs), 2)

		if ts_doc.docstatus == 1:
			ts_doc.flags.ignore_validate_update_after_submit = True
			ts_doc.flags.ignore_permissions = True

		try:

			ts_doc.save()

			ts_row.total_hours = ts_doc.total_hours
			ts_row.billable_hours = ts_doc.total_billable_hours

			updated_count += 1
			frappe.logger().info(
				f"[fix_mis_august_0008_timesheets] Updated {timesheet_name}: "
				f"{actual_hours}h total, {billing_hours}h billable"
			)

		except Exception as e:
			skipped_timesheets.append(f"{timesheet_name}: Error updating Timesheet - {str(e)}")

	if updated_count > 0:
		mis._recalculate_totals_from_timesheets_table()
		mis.save()
		mis.reload()

	if skipped_timesheets:
		frappe.logger().warning(
			"[fix_mis_august_0008_timesheets] Skipped timesheets:\n" + "\n".join(skipped_timesheets)
		)

	frappe.logger().info(
		f"[fix_mis_august_0008_timesheets] Done. Updated: {updated_count}, "
		f"Skipped: {len(skipped_timesheets)}"
	)
