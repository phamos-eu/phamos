// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Stakeholder Meeting", {
	refresh(frm) {
		frm.set_query("chapter", "chapter_reviews", () => ({
			filters: { implementation: frm.doc.implementation, status: ["!=", "Cancelled"] },
		}));
		frm.set_query("chapter", "decisions", () => ({
			filters: { implementation: frm.doc.implementation, status: ["!=", "Cancelled"] },
		}));
	},
});
