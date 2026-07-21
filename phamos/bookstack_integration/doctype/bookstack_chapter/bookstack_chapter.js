// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("Bookstack Chapter", {
	refresh(frm) {
		if (frm.doc.url) {
			frm.add_custom_button(__("Open in Bookstack"), () => window.open(frm.doc.url, "_blank"));
		}
	}
});
