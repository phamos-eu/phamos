// Copyright (c) 2026, phamos.eu and contributors
// Event Ticket Order: one order of the website with its tickets (phamos/phamos#1717). The status follows the
// tickets; Customer and Sales Order are created from here (phamos/phamos#1725).

frappe.ui.form.on("Event Ticket Order", {
	refresh(frm) {
		frm.disable_save();
	},
});
