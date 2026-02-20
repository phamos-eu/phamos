// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Implementation Summery", {
	refresh(frm) {
	},
	year(frm) {
		// Client-side validation: 4-digit year format
		const year = (frm.doc.year || "").toString().trim();
		if (!year) return;
		if (year.length !== 4 || !/^\d{4}$/.test(year)) {
			frm.set_intro(__("Year must be exactly 4 digits (e.g. 2024)."), "red");
			return;
		}
		const y = parseInt(year, 10);
		if (y < 2000 || y > 2100) {
			frm.set_intro(__("Year must be between 2000 and 2100."), "red");
			return;
		}
		frm.set_intro("");
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