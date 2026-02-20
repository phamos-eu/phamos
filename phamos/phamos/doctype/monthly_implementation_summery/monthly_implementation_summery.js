// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Monthly Implementation Summery", {
	refresh(frm) {
		// Add refresh button if all required fields are set
		if (frm.doc.implementation && frm.doc.year && frm.doc.month) {
			frm.add_custom_button(__("Refresh Timesheets"), function() {
				frm.call({
					method: "refresh_timesheets_api",
					doc: frm.doc,
					freeze: true,
					freeze_message: __("Refreshing timesheets..."),
					callback: function(r) {
						if (r.message) {
							frappe.show_alert({
								message: __("Timesheets refreshed: {0} timesheets found. Total Hours: {1}, Billable Hours: {2}", 
									[r.message.timesheets_count || 0, 
									 frappe.format(r.message.total_hours || 0, {fieldtype: "Float"}), 
									 frappe.format(r.message.billable_hours || 0, {fieldtype: "Float"})]),
								indicator: "green"
							}, 5);
							frm.reload_doc();
						}
					}
				});
			});
		}
	},
	
	implementation(frm) {
		// Auto-refresh when implementation changes
		if (frm.doc.implementation && frm.doc.year && frm.doc.month && !frm.is_new()) {
			frm.call({
				method: "refresh_timesheets_api",
				doc: frm.doc,
				callback: function() {
					frm.refresh_field("timesheets");
					frm.refresh_field("total_hours");
					frm.refresh_field("billable_hours");
					frm.refresh_field("total_hours_after_discount");
				}
			});
		}
	},
	
	year(frm) {
		// Auto-refresh when year changes
		if (frm.doc.implementation && frm.doc.year && frm.doc.month && !frm.is_new()) {
			frm.call({
				method: "refresh_timesheets_api",
				doc: frm.doc,
				callback: function() {
					frm.refresh_field("timesheets");
					frm.refresh_field("total_hours");
					frm.refresh_field("billable_hours");
					frm.refresh_field("total_hours_after_discount");
				}
			});
		}
	},
	
	month(frm) {
		// Auto-refresh when month changes
		if (frm.doc.implementation && frm.doc.year && frm.doc.month && !frm.is_new()) {
			frm.call({
				method: "refresh_timesheets_api",
				doc: frm.doc,
				callback: function() {
					frm.refresh_field("timesheets");
					frm.refresh_field("total_hours");
					frm.refresh_field("billable_hours");
					frm.refresh_field("total_hours_after_discount");
				}
			});
		}
	},
	
	discount(frm) {
		// Recalculate total hours after discount when discount changes
		if (frm.doc.billable_hours !== undefined) {
			frm.call({
				method: "calculate_totals",
				doc: frm.doc,
				callback: function() {
					frm.refresh_field("total_hours_after_discount");
				}
			});
		}
	}
});
