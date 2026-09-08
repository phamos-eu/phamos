import frappe


def execute():
	"""Submitted MIS created before the status field existed all defaulted to 'Draft'.
	Reset them to 'Open' and let auto-close logic reassert 'Closed' where fulfilled."""
	names = frappe.get_all(
		"Monthly Implementation Summary",
		filters={"docstatus": 1, "status": "Draft"},
		pluck="name",
	)
	for name in names:
		doc = frappe.get_doc("Monthly Implementation Summary", name)
		doc.status = "Open"
		doc.flags.ignore_permissions = True
		doc.flags.ignore_validate_update_after_submit = True
		doc.save()
		doc.sync_and_auto_close()
		frappe.db.commit()
