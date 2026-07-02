import frappe


def execute():

	if not frappe.db.table_exists("Implementation"):
		return

	fields = ["remaining_hrs", "total_hrs_timesheet", "delivered_total_hrs"]

	for field in fields:
		frappe.db.sql(f"""
			UPDATE `tabImplementation`
			SET `{field}` = 0
			WHERE `{field}` IS NULL
		""")

	frappe.db.commit()