import json

import frappe


def execute():
	"""Switch 'Employee Birthday' Auto Email Reports to the new rolling
	'Employee Upcoming Birthday' report.

	The stock 'Employee Birthday' report filters by a single, fixed calendar
	month, so an Auto Email Report built on it keeps sending the same month's
	birthdays forever regardless of when it actually runs. Point it at the new
	report instead, which always shows birthdays from today to one month out,
	and drop the now meaningless 'month' filter.
	"""
	names = frappe.get_all(
		"Auto Email Report",
		filters={"report": "Employee Birthday"},
		pluck="name",
	)

	for name in names:
		filters = frappe.db.get_value("Auto Email Report", name, "filters")
		filters = json.loads(filters) if filters else {}
		filters.pop("month", None)

		frappe.db.set_value(
			"Auto Email Report",
			name,
			{
				"report": "Employee Upcoming Birthday",
				"filters": json.dumps(filters),
			},
			update_modified=False,
		)
