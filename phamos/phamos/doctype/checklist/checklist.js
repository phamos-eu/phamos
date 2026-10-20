// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Checklist", {
	setup(frm) {
		// Items can only be assigned to employees (#1625), as checked on save.
		frm.set_query("assigned_to", "checklist_items", () => ({
			query: "phamos.api.checklist_inbox.checklist_owner_query",
		}));
	},
});
