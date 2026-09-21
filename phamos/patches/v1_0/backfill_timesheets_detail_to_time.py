import frappe


def execute():
	"""Backfill Timesheet Detail (time_logs) rows whose to_time is NULL.

	The Timesheet was historically created from Timesheet Record without
	setting `to_time` on the child `time_logs` row (see
	`phamos.phamos.doctype.timesheet_record.timesheet_record.TimesheetRecord.create_timesheet`).
	Each Timesheet Record already stores the correct `to_time`, so use that
	as the source of truth to backfill the linked Timesheet Detail rows.
	"""

	records = frappe.get_all(
		"Timesheet Record",
		filters={"docstatus": 1, "timesheet": ["is", "set"], "to_time": ["is", "set"]},
		fields=["name", "timesheet", "to_time"],
	)

	for record in records:
		time_log_names = frappe.get_all(
			"Timesheet Detail",
			filters={"parent": record.timesheet, "parenttype": "Timesheet", "to_time": ["is", "not set"]},
			pluck="name",
		)

		for time_log_name in time_log_names:
			frappe.db.set_value("Timesheet Detail", time_log_name, "to_time", record.to_time, update_modified=False)

	frappe.db.commit()