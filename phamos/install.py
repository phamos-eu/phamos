import frappe


def after_install():
	remove_default_leave_types()


def remove_default_leave_types():
	leave_types_to_remove = ["Casual Leave", "Compensatory Off", "Privilege Leave"]

	for leave_type in leave_types_to_remove:
		if frappe.db.exists("Leave Type", leave_type):
			frappe.delete_doc("Leave Type", leave_type, ignore_permissions=True, force=True)
