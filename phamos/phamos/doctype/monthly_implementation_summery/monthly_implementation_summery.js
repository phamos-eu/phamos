// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Implementation Summery", {
	refresh(frm) {
	},
	discount(frm) {
		// Validate discount is between 0 and 100
		if (frm.doc.discount !== undefined && frm.doc.discount !== null) {
			const discount = parseFloat(frm.doc.discount);
			if (isNaN(discount)) {
				frappe.msgprint(__("Discount must be a valid number."));
				frm.set_value("discount", null);
				return;
			}
			if (discount < 0) {
				frappe.msgprint(__("Discount cannot be negative. Please enter a value between 0 and 100."));
				frm.set_value("discount", 0);
				return;
			}
			if (discount > 100) {
				frappe.msgprint(__("Discount cannot exceed 100%. Please enter a value between 0 and 100."));
				frm.set_value("discount", 100);
				return;
			}
		}
		// Discount will be applied to billable_hours by server-side validate() method
		// The updated billable_hours will be shown after save/validation
	},
});