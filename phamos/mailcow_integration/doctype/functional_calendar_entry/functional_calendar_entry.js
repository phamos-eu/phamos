// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Functional Calendar Entry", {
	fetch_free_slots(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (window.phamos && phamos.functional_calendar) {
			phamos.functional_calendar.show_free_slots_dialog(frm, row, cdt, cdn);
		}
	},
});
