// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Account Assignment", {
	setup(frm) {
		frm.set_query("expense_account", () => ({
			filters: { company: frm.doc.company, root_type: "Expense", is_group: 0, disabled: 0 },
		}));
	},
});
