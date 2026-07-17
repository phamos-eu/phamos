// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Corrective Action Item", {
	to_be_implemented(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.parentfield !== "corrective_actions" || !row.to_be_implemented) {
			return;
		}
		frm.add_child("corrective_action_implementation", {
			action: row.action,
			owner: row.owner,
		});
		frm.refresh_field("corrective_action_implementation");
		frappe.show_alert({ message: __("Copied to D6"), indicator: "green" });
	},
});
