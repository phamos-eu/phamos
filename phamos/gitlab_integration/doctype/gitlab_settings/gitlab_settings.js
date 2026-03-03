// Copyright (c) 2025, phamos.eu and contributors
// For license information, please see license.txt

frappe.ui.form.on("GitLab Settings", {
	refresh(frm) {
        frm.add_custom_button('Sync Projects & Issues', function () {
            frappe.call({
                method: 'phamos.gitlab_integration.gitlab_utils.sync_gitlab_data',
                callback: function () {
                    frappe.msgprint("GitLab data synced!");
                }
            });
        });
	},
});
