// Copyright (c) 2026, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("KR", {
	refresh(frm) {
		// Create OKR linked to this KR (Parent KR) - user can set Parent OKR on the new form
		if (frm.doc.name) {
			frm.add_custom_button(__('Create OKR'), function() {
				frappe.new_doc('OKR', { parent_kra: frm.doc.name }).run();
			}, __('Create'));
		}
	},
});
