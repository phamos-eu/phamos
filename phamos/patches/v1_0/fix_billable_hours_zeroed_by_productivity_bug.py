import frappe


def execute():
	"""
	Fix Timesheet Records where percent_billable was incorrectly forced to 0
	because the stop dialog always sent productivity=100, even for non-internal
	projects. The backend treated any non-zero productivity as an override and
	set percent_billable=0.

	Affected records: submitted Timesheet Records on non-internal projects with
	percent_billable=0 that have a linked ERPNext Timesheet.

	Correction: restore percent_billable from the Project's own percent_billable
	field. If the project has no value set, default to 100.
	"""

	# Date range: from when the buggy code was deployed to present
	bug_introduced = "2026-06-22 00:00:00"

	records = frappe.db.sql("""
		SELECT
			tr.name,
			tr.timesheet,
			tr.actual_time,
			COALESCE(p.percent_billable, 100) AS correct_percent
		FROM `tabTimesheet Record` tr
		LEFT JOIN `tabProject` p ON p.name = tr.project
		WHERE tr.docstatus = 1
		  AND (tr.percent_billable = 0 OR tr.percent_billable IS NULL OR tr.percent_billable = '')
		  AND (p.custom_is_internal_project IS NULL OR p.custom_is_internal_project = 0)
		  AND tr.timesheet IS NOT NULL AND tr.timesheet != ''
		  AND tr.creation >= %(bug_introduced)s
	""", {"bug_introduced": bug_introduced}, as_dict=True)

	fixed_tr = 0
	fixed_ts = 0

	for r in records:
		correct_percent = float(r.correct_percent or 100)

		# Fix Timesheet Record
		frappe.db.set_value(
			"Timesheet Record", r.name,
			"percent_billable", correct_percent,
			update_modified=False
		)
		fixed_tr += 1

		# Fix the linked ERPNext Timesheet Detail row
		actual_hours = float(r.actual_time or 0) / 3600

		timesheet_rows = frappe.db.get_all(
			"Timesheet Detail",
			filters={"parent": r.timesheet},
			fields=["name", "hours"]
		)

		for row in timesheet_rows:
			row_hours = float(row.hours or actual_hours)
			billing_hours = round(row_hours * correct_percent / 100, 6)
			frappe.db.set_value(
				"Timesheet Detail", row.name,
				{
					"is_billable": 1,
					"billing_hours": billing_hours,
				},
				update_modified=False
			)

		fixed_ts += 1

	frappe.db.commit()
	frappe.logger().info(
		f"fix_billable_hours_zeroed_by_productivity_bug: "
		f"fixed {fixed_tr} Timesheet Records, {fixed_ts} Timesheets"
	)
