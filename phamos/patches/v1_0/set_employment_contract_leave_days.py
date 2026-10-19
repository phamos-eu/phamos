"""Employment Contracts created before #1628 get their leave days.

Adding the fields gave every existing row the column defaults (5 working days, 30 full-time
leave days) but no derived values. Employed contracts get Leave Days per Year and Leave Days
for Contract Period computed from those; Externals have no leave, so all four fields go to 0.
Recomputes from stored values only, so it is safe to run twice. HR should check the 30 days
against each existing contract.
"""

import frappe

from phamos.phamos.doctype.employment_contract.employment_contract import (
	get_leave_days_per_year,
	prorate_leave_days,
)


def execute():
	for row in frappe.get_all(
		"Employment Contract",
		fields=[
			"name",
			"contract_type",
			"effective_from",
			"valid_until",
			"working_days_per_week",
			"full_time_leave_days",
		],
	):
		if row.contract_type == "External":
			values = dict.fromkeys(
				("working_days_per_week", "full_time_leave_days", "leave_days_per_year", "leave_days_for_period"), 0
			)
		else:
			yearly = get_leave_days_per_year(row.full_time_leave_days, row.working_days_per_week)
			values = {
				"leave_days_per_year": yearly,
				"leave_days_for_period": prorate_leave_days(yearly, row.effective_from, row.valid_until),
			}
		frappe.db.set_value("Employment Contract", row.name, values, update_modified=False)
