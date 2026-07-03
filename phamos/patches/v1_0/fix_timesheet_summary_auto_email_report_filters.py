import json
import frappe


def execute():
	"""Set a default time_period filter on Timesheet Summary Auto Email Reports that have no filters set."""
	names = frappe.get_all(
		"Auto Email Report",
		filters={"report": "Timesheet Summary", "filters": ("in", ("", None))},
		pluck="name",
	)
	for name in names:
		frappe.db.set_value(
			"Auto Email Report",
			name,
			"filters",
			json.dumps({"time_period": "Last Week"}),
			update_modified=False,
		)
