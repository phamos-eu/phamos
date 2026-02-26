// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on('Job Opening', {
	refresh: function(frm) {
		if (!frm.is_new()) {
			frm.add_custom_button(__('Interview Configuration'), function() {
				frappe.set_route('Form', 'Recruitment Settings', 'Recruitment Settings');
				frappe.show_alert({
					message: __('Add or edit configuration for "{0}" in the Job Opening Configurations table', [frm.doc.name]),
					indicator: 'blue'
				}, 5);
			});
		}
	}
});

