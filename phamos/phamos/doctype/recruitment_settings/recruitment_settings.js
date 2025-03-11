// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Recruitment Settings", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Interview Booking Slots", {
	interview_slot(frm, ctd, cdn) {
		var d = locals[ctd][cdn];
		if (d.interview_slot) {
			frappe.call({
				method: "frappe.client.get",
				args: {
					doctype: "Interview Booking Slot",
					filters: { name: d.criteria_name },
				},
				callback: function (data) {
					frappe.model.set_value(ctd, cdn, "from_time", data.message.from_time);
					frappe.model.set_value(ctd, cdn, "to_time", data.message.to_time);
				},
			});
		}
	},
});